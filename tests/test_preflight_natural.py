"""The pre-flight of a run with natural PR-review tasks (``scripts/preflight_final_run.py``; protocol §15.5, §15.6,
§16.4, §17, §19, §20).

A synthetic family, NP-90, is laid out as an accepted natural family of the first sample whose verifiers, held-out pool,
labels and audits are complete, under a scratch repository (``data/natural/{tasks,snapshots}`` and the committed index),
and the whole pre-flight passes on it. Each test then breaks one rule:

* the base snapshot is looked up under ``data/natural/snapshots`` (``roots.snapshot_root``); the run id is
  ``natural-pr-v1`` or ``natural-pr-v2`` (§20.2, D71), and it must be new under ``data/natural/runs`` too;
* the pool is the pre-review state, 2 valid alternatives and 3 near misses, and nothing else;
* at least 2 of the 3 near misses name a scored active reference requirement introduced at a correction event (the
  review comment or a reply, ``session.metadata.events``);
* ``s10.json`` records ``passed`` and the committed index (not the working tree's) has ``s11`` true;
* the pre-review state carries its source-evidence label, invalid;
* every verifier (``task.json`` and ``verifiers_extra.json``, the reference checks and the labeler included) was
  frozen before the first pool candidate's generation started, and every pool candidate records that start in a
  complete generation record;
* the run grades the independent labeler; one that ``status.json`` does not call usable is a note, and a round other
  than 1 or 2 fails;
* B1 or B3 that the family's records show unavailable is a note, otherwise a missing condition;
* every agent of the natural recipe was audited with the natural-agent profile (the revisers and the labeler's revision
  as the records count them, and the mappers), and every flag (hit or exposure) is assessed;
* the run grades the accepted families of one sample (§20.2): ``natural-pr-v1`` every accepted family of the first sample
  (the index's ``sample``) and ``natural-pr-v2`` every one of the extension, never a family of the other sample, and
  nothing of another population; a row of the index that names no sample fails;
* building has stopped for the run's sample by the committed index (§20.2): for ``natural-pr-v1``, the S9 record shows the
  first sample screened with every family in the index, all processed, whatever the extension's state; for
  ``natural-pr-v2``, 30 accepted in all, or the same for the extension. A repository's open places are counted over both
  samples. Failing closed, a family that the S9 record lists for a sample needs a row that names that sample, and a row
  that names neither sample counts for both. §19.5's rule over both samples is kept for a run id that names neither run
  (the label proposer applies the rule of each family's own sample, D73, with the pre-flight's own functions for the
  accepted families of a sample and the rows that name no sample);
* every natural family the run grades has the lines of its phases P1 to P7 in the committed phase-end log, in order (D65,
  D73): the log of the HEAD commit only (not the working tree's, and no ``GIT_*`` variable redirects git); a log that git
  does not give, or one line that is not a phase-end record, fails the run; lines of other tasks do not count; the log
  that ``scripts/record_phase_end.py`` writes is read as it is written; and the docstrings say that the time condition
  of the order is the pre-flight's own reading and that the order of the log's commits stays the builder's record.

Controlled tasks are not affected: the existing pre-flight tests stay as they are, and neither a run of the four pilot
tasks nor a run of a synthetic task of another population reads the natural index or the phase-end log. Docker and ``git
status`` are not asked (the host is idle and clean); the scratch repository's own git answers ``git show``. Every text is
synthetic, with no login, handle, e-mail address or model identifier. These tests check code behaviour and are not
research evidence.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from natural_task_layout import (
    PHASE_END_SCHEMA,
    PHASE_ENDS,
    PHASES,
    commit_file,
    phase_end_line,
    phase_ends,
    write_phase_ends,
)

from tracecontract import natural_pr as npr
from tracecontract import roots
from tracecontract.analysis import PILOT_LABELER
from tracecontract.duplicates import same_code_duplicates
from tracecontract.patches import diff_dirs
from tracecontract.reconstruction import RECORD
from tracecontract.schemas import (
    AuditRecord,
    Author,
    Candidate,
    CandidateOrigin,
    ContractVariant,
    Eligibility,
    Event,
    EventKind,
    EvidenceSpan,
    Fidelity,
    GenerationRecord,
    Label,
    LabelerKind,
    Population,
    ProvenanceRecord,
    PRProvenance,
    RedactionStatus,
    Requirement,
    RequirementKind,
    RequirementStatus,
    Session,
    Snapshot,
    SnapshotSource,
    SourceRef,
    Split,
    TaskContract,
    TaskManifest,
    VerifierCondition,
    sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, load, write_json
from tracecontract.verifier import build_spec, freeze

R = Path(__file__).resolve().parents[1]
TID = "NP-90"
SID = "aidev-pr-9090"
T0 = "2026-11-21T10:00:00+00:00"  # the thread and the S10 build
FROZEN = "2026-11-22T09:00:00+00:00"  # when every verifier of the fixture was frozen
POOL_START = "2026-11-22T10:00:00+00:00"  # when the first pool candidate's generation started
CONDITIONS = ["initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform", "repo_tests",
              "diff_derived", "reference_check"]
RUN_ID = ["--run-id", "natural-pr-v1"]  # the natural run of the first sample's families (§20.2), NP-90's
OPTIONS = ["--repeats", "3", "--pilot", "--with-extra-verifiers", "--conditions", *CONDITIONS]
RUN = [*RUN_ID, *OPTIONS]
RUN_V2 = ["--run-id", "natural-pr-v2", *OPTIONS]  # the natural run of the extension's families (§20.2)
PR = 9090  # NP-90's PR id (its provenance)
# The index's S9 record when both samples are screened: the whole of each sample, and the families and reserves formed
# from it (NP-90 from the first sample; none from the extension).
S9_DONE = {"first": {"screened": 150, "families": [TID]}, "extension": {"screened": 534, "families": []}}

ISSUE = "add() should treat a missing value as zero. Calling add(None, 2) raises; it should return 2."
COMMENT = "This handles a missing first argument only; treat a missing second argument as zero too."
REPLY = "And add(None, None) should return 0."
EVENTS = {"issue": f"{SID}/issue", "reviewed": f"{SID}/commit/aaaaaaaaaaaa", "comment": f"{SID}/review/8100",
          "reply": f"{SID}/reply/8101", "addressing": f"{SID}/commit/bbbbbbbbbbbb"}
BASE_FILES = {"pkg/__init__.py": "", "pkg/mod.py": "def add(a, b):\n    return a + b\n",
              "tests/test_mod.py": "from pkg.mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"}
# The pkg/mod.py of each candidate state; every state differs from every other.
STATES = {
    "reference": "def add(a, b):\n    if a is None:\n        a = 0\n    if b is None:\n        b = 0\n    return a + b\n",
    "pre-review": "def add(a, b):\n    if a is None:\n        a = 0\n    return a + b\n",
    "eval-alt-1": "def add(a, b):\n    a = 0 if a is None else a\n    b = 0 if b is None else b\n    return a + b\n",
    "eval-alt-2": "def add(a, b):\n    return sum(x for x in (a, b) if x is not None)\n",
    "eval-nm-1": "def add(a, b):\n    if a is None:\n        return b\n    return a + b\n",
    "eval-nm-2": ("def add(a, b):\n    if a is None and b is None:\n        return None\n    a = 0 if a is None else a\n"
                  "    b = 0 if b is None else b\n    return a + b\n"),
    "eval-nm-3": "def add(a, b):\n    if b is None:\n        b = 0\n    return a + b\n",
}
# The reference contract: one requirement per user turn (issue, review comment, reply), and the near misses' targets.
REQUIREMENTS = {"R-first": "issue", "R-second": "comment", "R-both": "reply"}
TARGETS = {"eval-nm-1": "R-second", "eval-nm-2": "R-both", "eval-nm-3": "R-first"}
# Every entry of labels/generator_audit.json the fixture needs: the recipe's agents, one reviser of initial_audited
# (its audit record counts one revision), one reviewer of the reference checks and the two mappers.
AUDITS = ["contract-initial", "contract-full", "testgen-initial", "testgen-full", "freeform", "diff-derived",
          "attack-initial", "attack-full", "alt-initial", "alt-full", "revise-initial-1", "refcontract", "refcheck",
          "refcheck-review-1", "labeler", "eval-alt-1", "eval-alt-2", "eval-nm-1", "eval-nm-2", "eval-nm-3", "mapper-1",
          "mapper-2"]
NATURAL_PROFILE = "natural-agent:v1"  # scripts/audit_eval_generators.py --profile natural (controlled.NATURAL_PROFILE)


# --- the pre-flight module --------------------------------------------------------------------------------------------

def _preflight():
    spec = importlib.util.spec_from_file_location("preflight_final_run", R / "scripts" / "preflight_final_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def pf(monkeypatch):
    mod = _preflight()
    real = subprocess.run

    def run(cmd, *a, **k):  # the host is idle and the tree clean: only these two questions are answered here
        if list(cmd[:2]) in (["docker", "ps"], ["git", "status"]):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return real(cmd, *a, **k)

    monkeypatch.setattr(mod.subprocess, "run", run)
    from tracecontract.sandbox import docker_runner

    monkeypatch.setattr(docker_runner, "HARNESS_VERSION", "tc-harness/0.3.5")
    return mod


# --- the scratch repository -------------------------------------------------------------------------------------------

def _git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"GIT_CONFIG_GLOBAL": os.devnull,
                                                                                "GIT_CONFIG_NOSYSTEM": "1"}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=fixture", "-c", "user.email=", *args], check=True,
                   capture_output=True, env=_git_env())


INDEX = Path("data/manifests/natural_tasks_index.json")


def index_row(task_id: str = TID, *, s11: bool = True, outcome: str = "passed", repo_id: int = 990,
              role: str = "family", sample: object = "first") -> dict:
    return {"task_id": task_id, "role": role, "repo_id": repo_id, "sample": sample,
            "s10": {"outcome": outcome, "stage": "S10"}, "s11": s11}


_DONE = object()


def write_index(root: Path, rows: list[dict] | None = None, *, s9=_DONE, commit: bool = True) -> None:
    """The natural index under ``root`` (one row for NP-90 by default; the S9 record ``s9``, by default both samples
    screened with NP-90 the first sample's only family, and none with ``s9=None``), committed unless ``commit`` is
    false."""
    index = {"schema": "tracecontract/natural-tasks-index/v1", "population": "natural:pr-review",
             "s9_complete": S9_DONE if s9 is _DONE else s9, "tasks": [index_row()] if rows is None else rows}
    if s9 is None:
        index.pop("s9_complete")
    write_json(index, root / INDEX)
    if commit:
        _git(root, "add", "--", INDEX.as_posix())
        staged = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--quiet", "--", INDEX.as_posix()],
                                capture_output=True, env=_git_env(), check=False)
        if staged.returncode:  # something to commit
            _git(root, "commit", "-q", "--no-verify", "-m", "natural index (synthetic fixture)", "--", INDEX.as_posix())


# --- the synthetic family ---------------------------------------------------------------------------------------------

def _tree(dest: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_text(text, encoding="utf-8")
    return dest


def _patch(base: Path, mod: str, scratch: Path) -> str:
    state = scratch / "state"
    shutil.copytree(base, state)
    (state / "pkg" / "mod.py").write_text(mod, encoding="utf-8")
    patch = diff_dirs(base, state)
    shutil.rmtree(state)
    return patch


def _session() -> Session:
    def event(i: int, which: str, kind: EventKind, author: Author, text: str) -> Event:
        return Event(event_id=EVENTS[which], session_id=SID, index=i, kind=kind, author=author, timestamp=T0, text=text,
                     source=SourceRef(path="synthetic", line=i + 1))

    events = [event(0, "issue", EventKind.user_prompt, Author.human, ISSUE),
              event(1, "reviewed", EventKind.tool_call, Author.agent, "Treat a missing first argument as zero"),
              event(2, "comment", EventKind.user_prompt, Author.human, COMMENT),
              event(3, "reply", EventKind.user_prompt, Author.human, REPLY),
              event(4, "addressing", EventKind.tool_call, Author.agent, "Treat missing arguments as zero")]
    metadata = {"events": {"initial_request": EVENTS["issue"], "reviewed_commit": EVENTS["reviewed"],
                           "correction": EVENTS["comment"], "replies": [EVENTS["reply"]],
                           "addressing_commit": EVENTS["addressing"]}}
    return Session(session_id=SID, population=Population.natural_pr_review, source="synthetic",
                   source_format="aidev_pr_thread_v1", trace_sha256=sha256_text("synthetic thread"), events=events,
                   metadata=metadata)


def _requirement(rid: str, which: str, session: Session) -> Requirement:
    text = next(e.text for e in session.events if e.event_id == EVENTS[which])
    return Requirement(req_id=rid, statement=f"synthetic requirement {rid}", kind=RequirementKind.change,
                       status=RequirementStatus.explicit, introduced_at=EVENTS[which],
                       evidence=[EvidenceSpan(event_id=EVENTS[which], start=0, end=12, quote=text[:12])],
                       observable="a synthetic test", proposer="fixture")


def _contract(variant: ContractVariant, rids: list[str], session: Session) -> TaskContract:
    return TaskContract(contract_id=f"{TID}-{variant.value}", task_id=TID, session_id=SID, variant=variant,
                        requirements=[_requirement(r, REQUIREMENTS[r], session) for r in rids], created_by="fixture",
                        created_at=T0)


def d19(value: str) -> Label:
    return Label(value=value, labeler=PILOT_LABELER, labeler_kind=LabelerKind.model, timestamp=POOL_START)


def construction(value: str, violates: list[str] | None = None) -> Label:
    return Label(value=value, violated_requirements=violates or [], labeler="fixture:v1",
                 labeler_kind=LabelerKind.construction, timestamp=POOL_START)


def generation(kind: str, started_at: str | None = POOL_START) -> GenerationRecord:
    budget = {"started_at": started_at, "ended_at": "2026-11-22T10:30:00+00:00", "wall_s": 60.0, "turns": 3,
              "tool_calls": 5, "run_record": f"build-session:synthetic/{kind}.jsonl"}
    return GenerationRecord(generator="config-A", run_id=f"wf_fixture/{kind}", prompt_sha256="0" * 64,
                            created_at="2026-11-22T10:30:00+00:00",
                            budget={k: v for k, v in budget.items() if v is not None})


def _verifier(td: Path, vid: str, condition: VerifierCondition, iterations: int | None = None) -> str:
    tests = _tree(td / "verifiers" / vid / "tests", {f"test_{vid}.py": "def test_synthetic():\n    assert True\n"})
    spec = build_spec(verifier_id=vid, task_id=TID, condition=condition, test_dir=tests, task_dir=td)
    if iterations is not None:
        spec = spec.model_copy(update={"audit": AuditRecord(procedure="audit:v1", iterations=iterations, passed=True)})
    dump(freeze(spec, td).model_copy(update={"frozen_at": FROZEN}), td / "verifiers" / vid / "spec.json")
    return f"verifiers/{vid}/spec.json"


def candidate(kind: str, origin: CandidateOrigin, split: Split, patch: str, labels: list[Label],
              gen: GenerationRecord | None = None) -> Candidate:
    extra = {"generation": gen} if gen is not None else {}
    return Candidate(candidate_id=f"{TID}-{kind}", task_id=TID, origin=origin, split=split, patch=patch,
                     patch_sha256=sha256_text(patch), produced_by="fixture", labels=labels, **extra)


def build(root: Path) -> Path:
    """NP-90 under ``root``: complete and accepted, so that the whole pre-flight passes (see the module docstring)."""
    (root / ".gitignore").write_text("data/natural/\n/snapshots/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True, env=_git_env())
    td = root / "data" / "natural" / "tasks" / TID
    base = _tree(root / "data" / "natural" / "snapshots" / TID, BASE_FILES)
    scratch = root / ".scratch"
    scratch.mkdir()
    patches = {kind: _patch(base, mod, scratch) for kind, mod in STATES.items()}
    shutil.rmtree(scratch)
    session = _session()
    dump(session, td / "session.json")
    se = Label(value="invalid", labeler="source-evidence:aidev-s9", labeler_kind=LabelerKind.source_evidence, timestamp=T0)
    noop = construction("invalid")
    cands = [candidate("reference", CandidateOrigin.reference, Split.dev, patches["reference"], []),
             candidate("pre-review", CandidateOrigin.natural_pre_review, Split.eval, patches["pre-review"], [se, d19("invalid")]),
             candidate("noop-dev", CandidateOrigin.noop, Split.dev, "", [noop]),
             candidate("noop-eval", CandidateOrigin.noop, Split.eval, "", [noop])]
    cands += [candidate(k, CandidateOrigin.valid_alternative, Split.eval, patches[k], [construction("valid"), d19("valid")],
                        generation(k)) for k in ("eval-alt-1", "eval-alt-2")]
    cands += [candidate(k, CandidateOrigin.constructed_near_miss, Split.eval, patches[k],
                        [construction("invalid", [TARGETS[k]]), d19("invalid")], generation(k)) for k in TARGETS]
    for c in cands:
        dump(c, td / "candidates" / f"{c.candidate_id}.json")
    contracts = {ContractVariant.initial_only: ["R-first"], ContractVariant.full_session: list(REQUIREMENTS),
                 ContractVariant.reference: list(REQUIREMENTS)}
    for variant, rids in contracts.items():
        dump(_contract(variant, rids, session), td / "contracts" / f"{variant.value}.json")
    audited = {"initial_audited": 1, "full_audited": 0}  # revisions counted by each audited verifier's audit record
    specs = [_verifier(td, c, VerifierCondition(c), audited.get(c)) for c in CONDITIONS]
    write_json({"verifiers": [_verifier(td, "independent_label", VerifierCondition.reference_check)]},
               td / "verifiers_extra.json")
    write_json({"status": "usable", "round": 1, "reasons": ["synthetic"]}, td / "verifiers" / "independent_label" / "status.json")
    manifest_hash = manifest_sha256(manifest(base))
    dump(Snapshot(snapshot_id=f"{TID}@base", task_id=TID, repo_url="https://github.com/{owner}/fixture", base_commit="1" * 40,
                  fidelity=Fidelity.exact, file_manifest_sha256=manifest_hash, n_files=len(BASE_FILES)), td / "snapshot.json")
    pr = PRProvenance(dataset="synthetic", revision="0" * 40, pr_id=PR, pr_number=90, repo_id=990, agent="FixtureAgent",
                      comment_id=8100, reply_comment_ids=[8101], base_commit="1" * 40, base_rule="merge_base",
                      first_commit="2" * 40, reviewed_commit="3" * 40, addressing_commit="4" * 40,
                      merge_state="no_merges", fidelity=Fidelity.exact)
    dump(ProvenanceRecord(record_id=f"prov-{TID}", session_id=SID, population=Population.natural_pr_review,
                          source_url="https://example.invalid/synthetic", source_id="synthetic", permission_basis="fixture",
                          trace_sha256="0" * 64, snapshot_manifest_sha256=manifest_hash, capture_method="fixture",
                          redaction_status=RedactionStatus.redacted_by_us, task_family_id=TID,
                          eligibility=Eligibility.pending_review, accessed=T0, natural_pr=pr,
                          notes=json.dumps({"compiler": npr.COMPILER, "snapshot_root": "data/natural/snapshots"})),
         td / "provenance.json")
    dump(TaskManifest(task_id=TID, family_id=TID, population=Population.natural_pr_review, status="pending_review",
                      provenance="provenance.json", snapshot_source=SnapshotSource(repo_url="https://github.com/{owner}/fixture",
                                                                                   commit="1" * 40),
                      snapshot="snapshot.json", env_requirements=[], candidate_pythonpath="/work",
                      contracts={v.value: f"contracts/{v.value}.json" for v in contracts}, verifiers=specs,
                      candidates=[f"candidates/{c.candidate_id}.json" for c in cands]), td / "task.json")
    write_json({"task_id": TID, "stage": "S10", "outcome": "passed", "b1": {"available": True, "n_checks": 1}},
               td / "s10.json")
    write_pr_record(td)
    write_json(same_code_duplicates(td, root / "data" / "natural" / "snapshots"), td / "labels" / "duplicates.json")
    write_audits(td, AUDITS)
    write_index(root)
    write_phase_ends(root, phase_ends(TID))  # the end of each of its phases P1 to P7, committed (D65)
    return td


def write_pr_record(td: Path) -> None:
    """The PR reconstruction record of the current files, status passed (natural_pr.recorded_pr_check accepts it)."""
    checks = [{"check_id": cid, "title": title, "status": "passed"} for cid, title in npr.CHECK_TITLES.items()]
    write_json({"task_id": TID, "method": npr.PR_METHOD, "status": "passed", "passed": True, "checks": checks,
                "inputs": npr.pr_current_inputs(td)}, td / RECORD)


def audit_entry(ws: str, **fields) -> dict:
    """An entry of labels/generator_audit.json as scripts/audit_eval_generators.py --profile natural writes it, with no
    flag and an assessed strict re-audit, then ``fields``."""
    return {"transcript_sha256": "0" * 64, "profile": NATURAL_PROFILE, "hits": [], "exposures": [], "flagged": False,
            "strict_reaudit": {"assessment": "synthetic: no finding", "transcripts": {ws: {"sha256": "0" * 64}}}, **fields}


def write_audits(td: Path, names: list[str], **entries: dict) -> None:
    """labels/generator_audit.json: an unflagged natural-profile audit with a strict re-audit for each of ``names``, then
    ``entries``."""
    audit = {ws: audit_entry(ws) for ws in names}
    write_json({**audit, **entries, "_rules": {"script": "scripts/audit_eval_generators.py"}},
               td / "labels" / "generator_audit.json")


def edit(path: Path, change) -> None:
    """Rewrite the JSON file ``path`` with ``change(data)`` applied in place."""
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    write_json(data, path)


def edit_candidate(td: Path, kind: str, change) -> None:
    edit(td / "candidates" / f"{TID}-{kind}.json", change)


def edit_spec(td: Path, vid: str, **fields) -> None:
    edit(td / "verifiers" / vid / "spec.json", lambda s: s.update(fields))


def drop_candidate(td: Path, kind: str) -> None:
    edit(td / "task.json", lambda m: m["candidates"].remove(f"candidates/{TID}-{kind}.json"))


def drop_verifier(td: Path, vid: str) -> None:
    edit(td / "task.json", lambda m: m["verifiers"].remove(f"verifiers/{vid}/spec.json"))


def fixture_task(root: Path) -> Path:
    """FX-PF under ``root / "tasks"``: a task of the fixture population with a no-op only, as in
    tests/test_preflight_run_rules.py."""
    other = root / "tasks" / "FX-PF"
    noop = Candidate(candidate_id="FX-PF-noop-eval", task_id="FX-PF", origin=CandidateOrigin.noop, split=Split.eval, patch="",
                     patch_sha256=sha256_text(""), produced_by="base snapshot")
    dump(noop, other / "candidates" / "noop.json")
    dump(TaskManifest(task_id="FX-PF", family_id="FX-PF", population=Population.fixture, status="pending_review",
                      provenance="provenance.json", snapshot_source=SnapshotSource(repo_url="https://example.invalid/x",
                                                                                     commit="0" * 40),
                      env_requirements=[], candidates=["candidates/noop.json"]), other / "task.json")
    write_json({"snapshot_id": "FX-PF", "task_id": "FX-PF", "repo_url": "x", "base_commit": "0" * 40, "fidelity": "exact",
                "file_manifest_sha256": "0" * 64, "n_files": 0}, other / "snapshot.json")
    return other


def run(pf, root: Path, *argv: str, tasks: list[Path] | None = None, capsys) -> tuple[int, list[str], list[str]]:
    """``main`` on NP-90 (or ``tasks``) with the scratch repository as the pre-flight's root: (exit code, failures, notes)."""
    pf.R = root
    code = pf.main(*map(str, tasks or [root / "data" / "natural" / "tasks" / TID]), *argv)
    out = capsys.readouterr().out
    return code, _lines(out, "FAIL"), _lines(out, "NOTE")


def _lines(out: str, kind: str) -> list[str]:
    return [ln[len(kind) + 2:] for ln in out.splitlines() if ln.startswith(f"{kind}: ")]


@pytest.fixture()
def family(tmp_path) -> tuple[Path, Path]:
    """The scratch repository's root and NP-90's task directory."""
    return tmp_path, build(tmp_path)


# --- the complete family passes ---------------------------------------------------------------------------------------

def test_a_complete_natural_family_passes_the_whole_preflight(pf, family, capsys):
    root, _ = family
    code, fails, notes = run(pf, root, *RUN, capsys=capsys)
    assert (code, fails, notes) == (0, [], [])


def test_the_acceptance_gate_s_s10_and_index_reasons_are_not_repeated(pf, family, capsys):
    """The pre-flight reports the S10 record and the index row itself; the gate's reasons on them are not repeated, so
    a family that S10 did not pass fails once for it."""
    root, td = family
    edit(td / "s10.json", lambda s: s.update(outcome="built"))
    code, fails, _ = run(pf, root, *RUN, capsys=capsys)
    assert code == 1 and fails == [(f"{TID}: its S10 outcome (s10.json) is 'built', not 'passed'; only a family that passes "
                                    "S10 is built and run (protocol §15.6, §16.4)")]


# --- the snapshot root and the run id ----------------------------------------------------------------------------------

def test_the_base_snapshot_is_looked_up_under_data_natural_snapshots(pf, family, capsys):
    root, td = family
    assert pf.roots.snapshot_root(td, repo=root) == root / "data" / "natural" / "snapshots"
    (root / "snapshots").mkdir()
    shutil.move(root / "data" / "natural" / "snapshots" / TID, root / "snapshots" / TID)  # snapshots/ is not consulted
    code, fails, _ = run(pf, root, *RUN, capsys=capsys)
    assert code == 1 and fails == [(f"{TID}: base snapshot not built (data/natural/snapshots/{TID} does not exist; the S10 "
                                    "build writes a natural PR-review task's base, natural_pr.compile_pr_task, not "
                                    "`tracecontract snapshot`)")]
    shutil.move(root / "snapshots" / TID, root / "data" / "natural" / "snapshots" / TID)
    (root / "data" / "natural" / "snapshots" / TID / "pkg" / "mod.py").write_text("changed = True\n")
    assert run(pf, root, *RUN, capsys=capsys)[1] == [f"{TID}: base snapshot does not match its recorded manifest"]


def test_an_unusable_recorded_snapshot_root_fails(pf, family, capsys):
    root, td = family
    edit(td / "provenance.json", lambda p: p.update(notes=json.dumps({"snapshot_root": "/srv/snapshots"})))
    fails = run(pf, root, *RUN, capsys=capsys)[1]
    assert len(fails) == 1 and fails[0].startswith(f"{TID}: base snapshot: its recorded snapshot root is unusable (")


def test_the_run_id_must_be_new_under_data_natural_runs_too(pf, tmp_path):
    runs, natural = tmp_path / "results" / "runs", tmp_path / "data" / "natural" / "runs"
    (runs / "pilot-x").mkdir(parents=True)
    (natural / "natural-pr-v1").mkdir(parents=True)
    kw = {"repeats": 3, "harness": "tc-harness/0.3.5", "runs_root": runs, "natural_runs_root": natural}
    assert pf.run_problems(run_id="natural-pr-v2", **kw) == []
    assert pf.run_problems(run_id="natural-pr-v1", **kw) == [
        "run: data/natural/runs/natural-pr-v1 already exists; a new run needs a new run id (recorded runs are not changed)"]
    assert pf.run_problems(run_id="pilot-x", **kw) == [
        "run: results/runs/pilot-x already exists; a new run needs a new run id (recorded runs are not changed)"]
    assert pf.run_problems(run_id="natural-pr-v1", **{**kw, "natural_runs_root": None}) == []
    assert pf.run_problems.__kwdefaults__["natural_runs_root"] == roots.NATURAL_RUNS


TWO_RUNS = ("protocol §20.2 grades the natural arm in two runs, natural-pr-v1 for the accepted families of the first sample "
            "and natural-pr-v2 for those of the extension")


def test_a_natural_run_is_one_of_the_arm_s_two_runs(pf, family, capsys):
    """§20.2 fixes two natural runs, natural-pr-v1 and natural-pr-v2: without --run-id the check that the run is new would
    be skipped, and under another id a further natural run would pass."""
    root, _ = family
    assert run(pf, root, *OPTIONS, capsys=capsys)[1] == [
        (f"natural: pass --run-id natural-pr-v1 or natural-pr-v2 here and to evaluate: {TWO_RUNS}, and the pre-flight "
         "checks that the run has not been made")]
    for other in ("natural-pr-v1b", "natural-pr-v3", "natural-pr"):
        assert run(pf, root, "--run-id", other, *OPTIONS, capsys=capsys)[1] == [f"natural: the run id is {other!r}; {TWO_RUNS}"]
    assert run(pf, root, *RUN, capsys=capsys) == (0, [], [])
    (root / "data" / "natural" / "runs" / "natural-pr-v1").mkdir(parents=True)  # the run has been made
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        "run: data/natural/runs/natural-pr-v1 already exists; a new run needs a new run id (recorded runs are not changed)"]
    # natural-pr-v2 is the other run's id: refused here only because NP-90 is of the first sample
    assert run(pf, root, *RUN_V2, capsys=capsys)[1] == [
        ("natural: the run natural-pr-v2 includes families of the first sample (NP-90), but it grades the accepted families "
         "of the extension only, and natural-pr-v1 those of the first sample (protocol §20.2)")]


def test_the_run_id_is_checked_under_the_preflight_s_repository(pf, tmp_path, monkeypatch, capsys):
    """main checks the run id under its repository root R (results/runs and data/natural/runs), where every other check
    looks, and passes those roots to run_problems."""
    seen = {}
    monkeypatch.setattr(pf, "run_problems", lambda **kw: seen.update(kw) or [])
    td = build(tmp_path)
    run(pf, tmp_path, *RUN, tasks=[td], capsys=capsys)
    assert (seen["runs_root"], seen["natural_runs_root"]) == (tmp_path / "results" / "runs",
                                                              tmp_path / "data" / "natural" / "runs")
    assert seen["run_id"] == "natural-pr-v1"


# --- the pool --------------------------------------------------------------------------------------------------------

POOL_RULE = "(natural_pre_review 1, valid_alternative 2, constructed_near_miss 3, and nothing else; protocol §15.6)"


def test_the_pool_is_one_pre_review_state_two_alternatives_and_three_near_misses(pf, family, capsys):
    root, td = family
    drop_candidate(td, "eval-nm-3")  # the controlled pool's five near misses are not asked for; three are
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        (f"{TID}: held-out pool {{'constructed_near_miss': 2, 'valid_alternative': 2, 'natural_pre_review': 1}} is not a "
         f"natural PR-review family's {POOL_RULE}")]


def test_a_held_out_candidate_of_another_origin_breaks_the_pool(pf, family, capsys):
    root, td = family
    other = candidate("pre-correction", CandidateOrigin.observed_pre_correction, Split.eval, "", [d19("invalid")])
    dump(other, td / "candidates" / f"{other.candidate_id}.json")
    edit(td / "task.json", lambda m: m["candidates"].append(f"candidates/{other.candidate_id}.json"))
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        (f"{TID}: held-out pool {{'observed_pre_correction': 1, 'constructed_near_miss': 3, 'valid_alternative': 2, "
         f"'natural_pre_review': 1}} is not a natural PR-review family's {POOL_RULE}")]


# --- the near misses target the correction -----------------------------------------------------------------------------

NM_RULE = ("must name, in a construction label, a scored active requirement of the reference contract introduced at the "
           "review comment or a reply")


def _near_misses(pf, td: Path) -> list[str]:
    m = load(td / "task.json", TaskManifest)
    held = [load(td / p, Candidate) for p in m.candidates]
    held = [c for c in held if c.split == Split.eval and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]
    return pf.near_miss_problems(td, m, held)


def _retarget(td: Path, kind: str, violates: list[str], *, keep_d19: bool = True) -> None:
    edit_candidate(td, kind, lambda c: c.update(labels=[construction("invalid", violates).model_dump(mode="json")]
                                                + ([d19("invalid").model_dump(mode="json")] if keep_d19 else [])))


def test_two_of_the_three_near_misses_must_target_the_correction(pf, family, capsys):
    """nm-1 targets the review comment's requirement and nm-2 the reply's; nm-3 the issue's, which is allowed."""
    root, td = family
    assert _near_misses(pf, td) == []
    _retarget(td, "eval-nm-2", ["R-first"])
    expect = (f"{TID}: 1 of its 3 near misses target the correction; at least 2 {NM_RULE} (the reference contract has 2; "
              f"protocol §15.6): {TID}-eval-nm-2 names no scored active requirement introduced at a correction event; "
              f"{TID}-eval-nm-3 names no scored active requirement introduced at a correction event")
    assert _near_misses(pf, td) == [expect]
    assert run(pf, root, *RUN, capsys=capsys)[1] == [expect]


@pytest.mark.parametrize("case", ["unknown id", "no construction label", "two targets in one label"])
def test_what_a_near_miss_names_is_read_from_its_construction_labels(pf, tmp_path, case):
    td = build(tmp_path)
    if case == "unknown id":
        _retarget(td, "eval-nm-2", ["R-nowhere"])
        why = "names no requirement of the reference contract"
    elif case == "no construction label":
        edit_candidate(td, "eval-nm-2", lambda c: c.update(labels=[lb for lb in c["labels"] if lb["labeler_kind"] != "construction"]))
        why = "names no requirement in a construction label"
    else:  # one label naming the issue's requirement and the reply's counts as targeting the correction
        _retarget(td, "eval-nm-2", ["R-first", "R-both"])
        assert _near_misses(pf, td) == []
        return
    problems = _near_misses(pf, td)
    assert len(problems) == 1 and problems[0].startswith(f"{TID}: 1 of its 3 near misses target the correction")
    assert f"{TID}-eval-nm-2 {why}" in problems[0]


@pytest.mark.parametrize("case", ["unscored", "superseded", "reply not recorded", "no reference contract",
                                  "session unreadable"])
def test_only_scored_active_requirements_of_the_correction_events_count(pf, tmp_path, case):
    td = build(tmp_path)
    contract = td / "contracts" / "reference.json"
    if case == "unscored":
        edit(contract, lambda c: c["requirements"][2].update(scored=False))
    elif case == "superseded":  # R-both superseded by a later requirement introduced at the issue: not active
        def supersede(c):
            c["requirements"][2].update(status="superseded", superseded_by="R-first")
        edit(contract, supersede)
    elif case == "reply not recorded":  # the reply is a user turn, but the session does not record it as a reply
        edit(td / "session.json", lambda s: s["metadata"]["events"].update(replies=[]))
    elif case == "no reference contract":
        edit(td / "task.json", lambda m: m["contracts"].pop("reference"))
        assert _near_misses(pf, td) == [(f"{TID}: the task has no reference contract, so nothing shows that its near misses "
                                         "target the correction (protocol §15.6)")]
        return
    else:
        (td / "session.json").write_text("{not json")
        problems = _near_misses(pf, td)
        assert len(problems) == 1 and problems[0].startswith(f"{TID}: session.json does not load (")
        return
    problems = _near_misses(pf, td)
    assert len(problems) == 1 and problems[0].startswith(f"{TID}: 1 of its 3 near misses target the correction; at least 2")
    assert "(the reference contract has 1;" in problems[0] and f"{TID}-eval-nm-2 names no scored active" in problems[0]


# --- the S10 record and the committed index ----------------------------------------------------------------------------

def test_the_family_must_pass_s10(pf, family, capsys):
    root, td = family
    (td / "s10.json").unlink()
    fails = run(pf, root, *RUN, capsys=capsys)[1]
    assert f"{TID}: no readable s10.json, so nothing shows that the family passed S10 (protocol §15.6, §16.4)" in fails


def test_the_committed_index_row_must_be_s11(pf, family, capsys):
    """The committed index decides, not the working tree's (which natural-index rewrites before a commit)."""
    root, _ = family
    not_s11 = (f"{TID}: not S11 in the committed index (data/manifests/natural_tasks_index.json in the HEAD commit); S11 "
               "means passing S10 within the family cap (protocol §16.4)")
    write_index(root, [index_row(s11=False)])
    assert run(pf, root, *RUN, capsys=capsys)[1] == [not_s11]
    row = index_row()
    del row["s11"]  # a row that does not say s11 is not S11 (only true is)
    write_index(root, [row])
    assert run(pf, root, *RUN, capsys=capsys)[1] == [not_s11]
    write_index(root, [index_row(s11=True)], commit=False)  # changed, not committed
    assert run(pf, root, *RUN, capsys=capsys)[1] == [not_s11]
    write_index(root, [index_row(s11=True)])
    write_index(root, [index_row(s11=False)], commit=False)
    assert run(pf, root, *RUN, capsys=capsys)[1] == []
    write_index(root, [index_row("NP-91", repo_id=991)])
    fails = run(pf, root, *RUN, capsys=capsys)[1]
    assert f"{TID}: no row in the committed index (data/manifests/natural_tasks_index.json in the HEAD commit)" in fails


# --- the source-evidence label ---------------------------------------------------------------------------------------

def test_the_pre_review_state_carries_its_source_evidence_label(pf, family, capsys):
    root, td = family
    edit_candidate(td, "pre-review", lambda c: c.update(labels=[lb for lb in c["labels"] if lb["labeler_kind"] != "source_evidence"]))
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        (f"{TID}: {TID}-pre-review has no source-evidence label (labeler kind source_evidence), the label of the pre-review "
         "acceptance estimand (protocol §15.6)")]
    edit_candidate(td, "pre-review", lambda c: c["labels"].insert(0, {
        "value": "valid", "labeler": "source-evidence:aidev-s9", "labeler_kind": "source_evidence", "timestamp": T0}))
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        (f"{TID}: {TID}-pre-review: its source-evidence label is 'valid'; protocol §15.6 labels the pre-review state invalid "
         "with respect to the correction")]


# --- the verifiers were frozen before the pool was generated -----------------------------------------------------------

@pytest.mark.parametrize("vid, where", [("reference_check", "task.json"), ("initial_plain", "task.json"),
                                        ("independent_label", "verifiers_extra.json")])
def test_every_verifier_was_frozen_before_the_pool_was_generated(pf, tmp_path, capsys, vid, where):
    root, td = tmp_path, build(tmp_path)
    late = "2026-11-22T11:00:00+01:00"  # 10:00Z, the same second as the pool's first start: not before it
    edit_spec(td, vid, frozen_at=late)
    assert run(pf, root, *RUN, capsys=capsys)[1] == [  # every pool candidate starts at POOL_START; the first listed counts
        (f"{TID}: verifier {vid} ({where}) was frozen at {late}, not before the first candidate of the held-out pool was "
         f"generated ({TID}-eval-alt-1, started at {POOL_START}); protocol §19.7 freezes a family's verifiers before its "
         "held-out pool is generated")]
    edit_spec(td, vid, frozen_at="2026-11-22T09:59:59+00:00")
    assert run(pf, root, *RUN, capsys=capsys)[1] == []


def test_the_earliest_pool_start_counts(pf, family, capsys):
    """One near miss generated before the fixture's verifiers were frozen (09:00Z): every frozen verifier fails, those of
    task.json and the labeler of the sidecar."""
    root, td = family
    early = "2026-11-22T08:00:00Z"
    edit_candidate(td, "eval-nm-3", lambda c: c["generation"]["budget"].update(started_at=early))
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        f"{TID}: verifier {vid} ({where}) was frozen at {FROZEN}, not before the first candidate of the held-out pool was "
        f"generated ({TID}-eval-nm-3, started at {early}); protocol §19.7 freezes a family's verifiers before its held-out "
        "pool is generated"
        for vid, where in [*((c, "task.json") for c in CONDITIONS), ("independent_label", "verifiers_extra.json")]]


def test_a_pool_candidate_without_a_start_or_a_verifier_without_a_freezing_time_fails(pf, family, capsys):
    root, td = family
    edit_candidate(td, "eval-alt-2", lambda c: c["generation"]["budget"].pop("started_at"))
    no_start = (f"{TID}: {TID}-eval-alt-2 records no start of its generation (generation.budget.started_at, with a time "
                "zone), so nothing shows that the family's verifiers were frozen before it was generated (protocol §15.5, "
                "§19.7)")
    assert run(pf, root, *RUN, capsys=capsys)[1] == [no_start]
    edit_candidate(td, "eval-alt-2", lambda c: c["generation"]["budget"].update(started_at="2026-11-22T10:00:00"))
    assert run(pf, root, *RUN, capsys=capsys)[1] == [no_start]  # a time without a time zone is no start
    edit_candidate(td, "eval-alt-2", lambda c: c["generation"]["budget"].update(started_at=POOL_START))
    for frozen_at in (None, "2026-11-22T09:00:00"):
        edit_spec(td, "full_plain", frozen_at=frozen_at)
        assert run(pf, root, *RUN, capsys=capsys)[1] == [
            (f"{TID}: verifier full_plain (task.json) records no time of freezing (frozen_at {frozen_at!r}), so nothing "
             "shows that it was frozen before the held-out pool was generated (protocol §15.5, §19.7)")]


def test_a_pool_candidate_s_generation_record_must_be_complete(pf, family, capsys):
    """The start of a pool candidate's generation is the freezing order's evidence: a record that holds that start and
    nothing else (no run id, prompt hash or run-record pointer), as a hand-registered candidate might, fails (§15.6)."""
    root, td = family
    bare = {"generator": "config-A", "run_id": "", "prompt_sha256": "", "created_at": POOL_START,
            "budget": {"started_at": POOL_START}}
    edit_candidate(td, "eval-nm-1", lambda c: c.update(generation=bare))
    fails = run(pf, root, *RUN, capsys=capsys)[1]
    assert len(fails) == 1, fails
    assert fails[0].startswith(f"{TID}: {TID}-eval-nm-1: its generation record is not complete (run id missing")
    assert "prompt sha256 missing" in fails[0] and "pointer to the private run record missing" in fails[0]
    assert fails[0].endswith("its start is the evidence that the family's verifiers were frozen before it was generated "
                             "(§15.5, §19.7)")
    _, fails, notes = run(pf, root, *RUN, "--strata", "fresh-v1", "--only-strata", capsys=capsys)  # a pool check
    assert any(n.startswith(f"{TID}: {TID}-eval-nm-1: its generation record is not complete") for n in notes)


def test_the_freezing_order_reads_the_sidecar_whatever_the_options(pf, tmp_path):
    """The labeler is in verifiers_extra.json: its freezing time is checked even without --with-extra-verifiers."""
    td = build(tmp_path)
    m = load(td / "task.json", TaskManifest)
    side = pf.sidecar_specs(td, m)
    assert [(rel, s.verifier_id) for rel, s in side] == [("verifiers/independent_label/spec.json", "independent_label")]
    (td / "verifiers_extra.json").write_text("{not json")
    assert pf.sidecar_specs(td, m) == []  # reported by --with-extra-verifiers, which a natural run needs


# --- the independent labeler --------------------------------------------------------------------------------------------

def test_a_natural_run_grades_the_independent_labeler(pf, family, capsys):
    root, td = family
    argv = [*RUN_ID, "--repeats", "3", "--pilot", "--conditions", *CONDITIONS]
    assert run(pf, root, *argv, capsys=capsys)[1] == [
        (f"{TID}: a natural PR-review run grades the family's independent labeler (independent_label, registered in "
         "verifiers_extra.json); pass --with-extra-verifiers here and to evaluate (protocol §15.5, §15.6)")]
    no_labeler = (f"{TID}: the run grades no independent labeler (verifier independent_label of verifiers_extra.json, "
                  "condition 'reference_check'); its verdicts are the second labeling of a natural PR-review family "
                  "(protocol §15.5, §15.6)")
    conditions = [c for c in CONDITIONS if c != "reference_check"]
    fails = run(pf, root, *RUN_ID, "--repeats", "3", "--pilot", "--with-extra-verifiers", "--conditions", *conditions,
                capsys=capsys)[1]
    assert no_labeler in fails
    assert run(pf, root, *RUN_ID, "--repeats", "3", "--pilot", "--with-extra-verifiers", capsys=capsys)[1] == []  # all
    # A labeler registered in task.json (the recipe registers it in the sidecar) is graded without the option.
    edit(td / "task.json", lambda m: m["verifiers"].append("verifiers/independent_label/spec.json"))
    (td / "verifiers_extra.json").unlink()
    assert run(pf, root, *argv, capsys=capsys)[1] == []
    assert no_labeler in run(pf, root, *RUN_ID, "--repeats", "3", "--pilot", "--conditions", *conditions, capsys=capsys)[1]


def test_a_labeler_that_is_not_usable_is_a_note(pf, family, capsys):
    root, td = family
    status = td / "verifiers" / "independent_label" / "status.json"
    write_json({"status": "unusable", "round": 1, "reasons": ["synthetic"]}, status)
    code, fails, notes = run(pf, root, *RUN, capsys=capsys)
    assert (code, fails) == (0, []) and notes == [
        (f"{TID}: the independent labeler is not usable for this family (verifiers/independent_label/status.json says "
         "'unusable'); the second labeling leaves it out (protocol §15.5)")]
    status.unlink()
    code, fails, notes = run(pf, root, *RUN, capsys=capsys)
    assert (code, fails) == (0, []) and notes == [
        (f"{TID}: the independent labeler is not usable for this family (no readable verifiers/independent_label/"
         "status.json); the second labeling leaves it out (protocol §15.5)")]
    # Only "usable" is usable: a record that says nothing, or something else, is not.
    for record, said in (({"round": 1}, "None"), ({"status": "Usable", "round": 1}, "'Usable'")):
        write_json(record, status)
        code, fails, notes = run(pf, root, *RUN, capsys=capsys)
        assert (code, fails) == (0, []) and notes == [
            (f"{TID}: the independent labeler is not usable for this family (verifiers/independent_label/status.json says "
             f"{said}); the second labeling leaves it out (protocol §15.5)")]


LABELER_ROUND = ("an independent labeler records round 1 as written or round 2 after its one revision (protocol §15.5, "
                 "§19.8), and is reported unusable if it still fails")


@pytest.mark.parametrize("record, recorded", [
    ({"status": "usable", "round": 3}, "round 3"),  # revised twice: §15.5 allows one revision
    ({"status": "unusable", "round": 3}, "round 3"),
    ({"status": "usable"}, "no round"),  # nothing shows whether a revision (whose audit is needed) exists
    ({"status": "usable", "round": 0}, "round 0"),
    ({"status": "usable", "round": "2"}, "round '2'"),
    ({"status": "usable", "round": True}, "round True"),
])
def test_a_labeler_records_round_1_or_2(pf, tmp_path, capsys, record, recorded):
    root, td = tmp_path, build(tmp_path)
    write_json({**record, "reasons": ["synthetic"]}, td / "verifiers" / "independent_label" / "status.json")
    write_audits(td, [*AUDITS, "labeler-revision"])  # its revision's audit is there: the round alone fails
    code, fails, notes = run(pf, root, *RUN, capsys=capsys)
    assert (code, notes) == (1, []) and fails == [
        f"{TID}: the independent labeler: verifiers/independent_label/status.json records {recorded}; {LABELER_ROUND}"]


def test_a_revised_labeler_needs_the_audit_of_its_revision(pf, family, capsys):
    root, td = family
    write_json({"status": "usable", "round": 2, "reasons": ["synthetic"]}, td / "verifiers" / "independent_label" / "status.json")
    assert run(pf, root, *RUN, capsys=capsys)[1] == [f"{TID}: generator audits missing for ['labeler-revision']"]
    write_audits(td, [*AUDITS, "labeler-revision"])
    assert run(pf, root, *RUN, capsys=capsys)[1] == []


# --- B1 and B3 unavailable ---------------------------------------------------------------------------------------------

def test_b1_that_s10_records_unavailable_is_a_note(pf, family, capsys):
    root, td = family
    drop_verifier(td, "repo_tests")
    missing = f"{TID}: no verifier for condition(s) ['repo_tests']"
    assert run(pf, root, *RUN, capsys=capsys)[1] == [missing]  # s10.json records B1 as available: it is missing
    edit(td / "s10.json", lambda s: s.update(b1={"available": False, "reason": "synthetic"}))
    code, fails, notes = run(pf, root, *RUN, capsys=capsys)
    assert (code, fails) == (0, []) and notes == [
        (f"{TID}: B1 (repo_tests) is unavailable for this family: s10.json records it as unavailable (b1.available false; "
         "protocol §17.2, not a rejection); the run has no B1 verdict for it")]


def test_b3_whose_selection_kept_no_test_is_a_note(pf, family, capsys):
    root, td = family
    selection = td / "verifiers" / "diff_derived" / "selection.json"
    write_json({"task_id": TID, "verifier_id": "diff_derived", "condition": "diff_derived", "b3_available": False,
                "kept": [], "removed": ["test_diff_derived.py::test_synthetic"]}, selection)
    edit_spec(td, "diff_derived", frozen=False, frozen_at=None, checks_sha256=None)  # as the selection leaves it
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        (f"{TID}: verifier diff_derived not frozen; its test selection kept no test (verifiers/diff_derived/selection.json, "
         "b3_available false), so B3 is unavailable and this verifier must be kept out of the run "
         "(scripts/select_b3_tests.py)")]
    drop_verifier(td, "diff_derived")
    code, fails, notes = run(pf, root, *RUN, capsys=capsys)
    assert (code, fails) == (0, []) and notes == [
        (f"{TID}: B3 (diff_derived) is unavailable for this family: its test selection kept no test "
         "(verifiers/diff_derived/selection.json, b3_available false; scripts/select_b3_tests.py); the run has no B3 verdict "
         "for it")]
    edit(selection, lambda s: s.update(b3_available=True))
    assert run(pf, root, *RUN, capsys=capsys)[1] == [f"{TID}: no verifier for condition(s) ['diff_derived']"]
    selection.unlink()
    assert run(pf, root, *RUN, capsys=capsys)[1] == [f"{TID}: no verifier for condition(s) ['diff_derived']"]


# --- the audits of the natural recipe's agents -------------------------------------------------------------------------

@pytest.mark.parametrize("ws", ["contract-full", "testgen-initial", "diff-derived", "attack-full", "alt-initial",
                                "revise-initial-1", "refcontract", "refcheck", "refcheck-review-1", "labeler", "mapper-1",
                                "mapper-2"])
def test_every_agent_of_the_natural_recipe_was_audited(pf, tmp_path, capsys, ws):
    root, td = tmp_path, build(tmp_path)
    write_audits(td, [a for a in AUDITS if a != ws])
    assert run(pf, root, *RUN, capsys=capsys)[1] == [f"{TID}: generator audits missing for [{ws!r}]"]


def test_the_revisers_follow_the_audit_records_and_any_reviewer_will_do(pf, family, capsys):
    root, td = family
    edit_spec(td, "full_audited", audit={"procedure": "audit:v1", "iterations": 2, "passed": False, "findings": [],
                                         "dev_candidate_ids": []})
    assert run(pf, root, *RUN, capsys=capsys)[1] == [f"{TID}: generator audits missing for ['revise-full-1', 'revise-full-2']"]
    write_audits(td, [*[a for a in AUDITS if a != "refcheck-review-1"], "revise-full-1", "revise-full-2", "refcheck-review-2"])
    assert run(pf, root, *RUN, capsys=capsys)[1] == []


def test_missing_audits_of_pool_generators_are_problems_of_the_pool(pf, family, capsys):
    """They are failed apart from the others, and are notes with --only-strata (the run then does not grade the pool)."""
    root, td = family
    write_audits(td, [a for a in AUDITS if a not in ("eval-nm-2", "contract-initial")])
    assert run(pf, root, *RUN, capsys=capsys)[1] == [f"{TID}: generator audits missing for ['contract-initial']",
                                                     f"{TID}: generator audits missing for ['eval-nm-2']"]
    _, fails, notes = run(pf, root, *RUN, "--strata", "fresh-v1", "--only-strata", capsys=capsys)
    assert f"{TID}: generator audits missing for ['contract-initial']" in fails
    assert notes == [f"{TID}: generator audits missing for ['eval-nm-2'] ({pf.NOT_GRADED})"]


UNASSESSED = "every hit and exposure of the natural-agent profile is assessed in writing (assessment)"
NOT_NATURAL = ("not 'natural-agent:v1'; scripts/audit_eval_generators.py --task-dir <task dir> --profile natural audits "
               "every natural agent's tool inputs and outputs)")


def test_every_entry_present_is_checked_also_beyond_the_required_roles(pf, family, capsys):
    """A checker (optional) audited with the controlled substring rule: no natural profile, an unassessed hit and no
    strict re-audit."""
    root, td = family
    write_audits(td, AUDITS, checker={"hits": [{"tool": "Read", "match": "x", "text": "x"}]})
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        f"{TID}: generator audit checker was not made with the natural-agent profile (its profile is None, {NOT_NATURAL}",
        f"{TID}: generator audit checker has unassessed flags (1 hit(s)); {UNASSESSED}",
        f"{TID}: generator audit checker has no strict re-audit (scripts/strict_reaudit.py, D44)"]


HIT = {"tool": "Read", "path": "/elsewhere/x", "why": "outside the workspace", "text": "synthetic"}
EXPOSURE = {"tool": "Bash", "path": "/elsewhere/x", "why": "outside the workspace", "text": "synthetic"}


@pytest.mark.parametrize("flags, shown", [
    ({"exposures": [EXPOSURE], "flagged": True}, "1 exposure(s)"),  # tool outputs only: flagged all the same
    ({"hits": [HIT], "flagged": True}, "1 hit(s)"),
    ({"hits": [HIT], "exposures": [EXPOSURE, EXPOSURE], "flagged": True}, "1 hit(s), 2 exposure(s)"),
    ({"exposures": [EXPOSURE]}, "1 exposure(s)"),  # an exposure is a flag whatever 'flagged' says
    ({"flagged": True}, "flagged"),
])
def test_a_flagged_natural_audit_needs_a_written_assessment(pf, tmp_path, capsys, flags, shown):
    """natural-agent:v1 flags tool inputs (hits) and tool outputs (exposures), and every flag is assessed in writing; the
    strict re-audit's own assessment does not stand in for the entry's."""
    root, td = tmp_path, build(tmp_path)
    write_audits(td, AUDITS, **{"eval-nm-1": audit_entry("eval-nm-1", **flags)})
    unassessed = f"{TID}: generator audit eval-nm-1 has unassessed flags ({shown}); {UNASSESSED}"
    assert run(pf, root, *RUN, capsys=capsys)[1] == [unassessed]
    _, _, notes = run(pf, root, *RUN, "--strata", "fresh-v1", "--only-strata", capsys=capsys)
    assert f"{unassessed} ({pf.NOT_GRADED})" in notes  # a pool generator's audit: a note when the pool is not graded
    write_audits(td, AUDITS, **{"eval-nm-1": audit_entry("eval-nm-1", **flags, assessment="synthetic: assessed")})
    assert run(pf, root, *RUN, capsys=capsys)[1] == []


@pytest.mark.parametrize("profile", [None, "controlled", "fresh attempt"])
def test_every_natural_audit_was_made_with_the_natural_agent_profile(pf, tmp_path, capsys, profile):
    """An entry of another profile (the controlled substring rule reads tool inputs only) fails, also for an unflagged
    agent; for the reference checks' writer it fails whatever the run grades."""
    root, td = tmp_path, build(tmp_path)
    entry = {k: v for k, v in audit_entry("refcheck").items() if k != "profile"}
    write_audits(td, AUDITS, refcheck=entry if profile is None else {**entry, "profile": profile})
    other = (f"{TID}: generator audit refcheck was not made with the natural-agent profile (its profile is {profile!r}, "
             f"{NOT_NATURAL}")
    assert run(pf, root, *RUN, capsys=capsys)[1] == [other]
    assert other in run(pf, root, *RUN, "--strata", "fresh-v1", "--only-strata", capsys=capsys)[1]


def test_an_audit_entry_that_is_not_a_record_fails(pf, family, capsys):
    root, td = family
    write_audits(td, AUDITS, refcheck=["not", "a", "record"])
    assert run(pf, root, *RUN, capsys=capsys)[1] == [f"{TID}: generator audit refcheck is not an audit record (a JSON object)"]


def test_the_natural_audit_profile_is_wp_d_s():
    """The profile the pre-flight asks of a natural entry is the one scripts/audit_eval_generators.py --profile natural
    writes (tracecontract.controlled.NATURAL_PROFILE); the pre-flight keeps its own copy so that it does not import
    the audit code."""
    from tracecontract import controlled

    assert _preflight().NATURAL_AUDIT_PROFILE == controlled.NATURAL_PROFILE == NATURAL_PROFILE


def test_the_pool_checks_of_a_natural_family_are_notes_with_only_strata(pf, family, capsys):
    root, td = family
    _retarget(td, "eval-nm-2", ["R-first"])
    edit_candidate(td, "eval-alt-1", lambda c: c["generation"]["budget"].pop("started_at"))
    _, fails, notes = run(pf, root, *RUN, "--strata", "fresh-v1", "--only-strata", capsys=capsys)
    assert len(fails) == 1 and fails[0].startswith(f"{TID}: stratum fresh-v1 does not load: {TID} has no stratum 'fresh-v1'")
    assert len(notes) == 2 and all(n.endswith(f"({pf.NOT_GRADED})") for n in notes)
    assert notes[0].startswith(f"{TID}: 1 of its 3 near misses target the correction")
    assert notes[1].startswith(f"{TID}: {TID}-eval-alt-1 records no start of its generation")


# --- building has stopped, and the run grades every accepted family of its sample --------------------------------------

# §19.5 over both samples: the rule without a sample, kept for a run id that names neither run (the label proposer applies
# the rule of the family's own sample, D73).
STOP = ("natural: building has not stopped by the committed index: it counts {n} accepted task(s) of both samples, and "
        "protocol §19.5 stops building at 30 or when every family of both samples has been processed; {why}. No natural "
        "verifier is graded on a held-out candidate before building stops (§19.7)")
# §20.2: the rule of each run's sample.
STOP_FIRST = ("natural: building has not stopped for the first sample by the committed index: protocol §20.2 grades its "
              "accepted families in natural-pr-v1 once S9 is complete for it and every family and reserve of it has been "
              "processed; {why}. No natural verifier is graded on a held-out candidate of a family before that family's run "
              "(§20.2)")
STOP_EXTENSION = ("natural: building has not stopped for the extension by the committed index: it counts {n} accepted "
                  "task(s) in all, and protocol §20.2 grades the extension's accepted families in natural-pr-v2 at 30 "
                  "accepted tasks in all or once every family and reserve of the extension has been processed; {why}. No "
                  "natural verifier is graded on a held-out candidate of a family before that family's run (§20.2)")
NO_S9 = ("S9 is not recorded as complete for the {sample} sample (s9_complete.{sample} in the index is {what}, not the number "
         "of its comments screened and the task ids of its families and reserves)")


def listed_elsewhere(sample: str, ids: str) -> str:
    """s9_problems' reason for the families that the S9 record lists for ``sample`` whose rows name the other sample or
    neither."""
    return (f"{len(ids.split(', '))} of the {sample} sample's families and reserves (s9_complete.{sample}.families) have a "
            f"row in the index that names the other sample or neither ({ids})")


def test_building_stops_at_30_accepted_tasks_or_when_every_family_was_processed(pf):
    """Without a sample: §19.5 for both samples together."""
    rows = [index_row(f"NP-{n:02d}", repo_id=n) for n in range(1, 31)]
    assert pf.building_problems({"tasks": rows}, None) == []  # 30 accepted: stopped, whatever else the index says
    rows = rows[:29] + [index_row("NP-30", s11=False, outcome="not built", repo_id=30)]
    nothing = "; ".join(NO_S9.format(sample=s, what="absent") for s in ("first", "extension"))
    pending = "1 family of a repository with an open place has no S10 outcome (NP-30)"
    # The index natural-index writes today records no S9 completion: building has not stopped.
    assert pf.building_problems({"tasks": rows}, None) == [STOP.format(n=29, why=f"{nothing}; {pending}")]
    done = {"first": {"screened": 150, "families": [r["task_id"] for r in rows]},
            "extension": {"screened": 534, "families": []}}
    assert pf.building_problems({"tasks": rows, "s9_complete": done}, None) == [STOP.format(n=29, why=pending)]
    rows[-1] = index_row("NP-30", s11=False, outcome="rejected", repo_id=30)
    assert pf.building_problems({"tasks": rows, "s9_complete": done}, None) == []
    assert pf.building_problems(None, "a reason") == [
        ("natural: the committed index (data/manifests/natural_tasks_index.json in the HEAD commit) cannot be read (a "
         "reason), so nothing shows that building has stopped or which families are accepted (protocol §16.4, §19.5, "
         "§20.2)")]


NOT_TASK_IDS = ("s9_complete.extension.families is not a list of task ids, so nothing shows which families the extension "
                "sample yields")


def _s9(**samples) -> dict:
    """S9_DONE with the samples given replaced (None: left out)."""
    record = {**S9_DONE, **samples}
    return {k: v for k, v in record.items() if v is not None}


@pytest.mark.parametrize("record, why", [
    # a bare flag shows neither how much of the sample was screened nor which families it yields
    ({"first": True, "extension": True}, [NO_S9.format(sample="first", what="true"),
                                          NO_S9.format(sample="extension", what="true")]),
    (_s9(extension=None), [NO_S9.format(sample="extension", what="absent")]),
    (_s9(extension={"screened": 533, "families": []}),
     ["S9 has not screened the whole extension sample (s9_complete.extension.screened is 533, the sample has 534 comments)"]),
    (_s9(first={"screened": "150", "families": [TID]}),
     ["S9 has not screened the whole first sample (s9_complete.first.screened is '150', the sample has 150 comments)"]),
    (_s9(extension={"screened": 534}),
     [NOT_TASK_IDS]),
    (_s9(extension={"screened": 534, "families": [26]}), [NOT_TASK_IDS]),
    # the extension's families are not in the index yet (they have no rows): S9's record alone does not stop building
    (_s9(extension={"screened": 534, "families": ["NP-27", "NP-26"]}),
     [("2 of the extension sample's families and reserves (s9_complete.extension.families) have no row in the index "
       "(NP-26, NP-27)")]),
    ("complete", ["s9_complete in the index is \"complete\", not an S9 record by sample"]),
])
def test_the_s9_record_shows_both_samples_screened_with_every_family_in_the_index(pf, record, why):
    """§19.5's second branch: every family of both samples processed. It needs S9 complete for both samples (the whole
    sample screened: 150 comments, 534 for the extension) and a row in the index for every family and reserve that S9's
    samples yield, so that a family missing from the index cannot count as processed."""
    index = {"tasks": [index_row()], "s9_complete": record}
    assert pf.s9_problems(index) == why
    assert pf.building_problems(index, None) == [STOP.format(n=1, why="; ".join(why))]
    assert pf.s9_problems({"tasks": [index_row()], "s9_complete": S9_DONE}) == []
    assert pf.building_problems({"tasks": [index_row()], "s9_complete": S9_DONE}, None) == []


def test_a_family_is_processed_when_its_repository_has_no_open_place(pf):
    """At most 2 families per repository (§15.6): once a repository has 2 accepted families its other rows (reserves, or an
    extension family §19.3 does not build) need no S10 outcome; otherwise each row needs one."""
    full = [index_row("NP-04", repo_id=7), index_row("NP-05", repo_id=7),
            index_row("NP-23", s11=False, outcome="not built", repo_id=7, role="reserve")]
    open_ = [index_row("NP-01", s11=False, outcome="rejected", repo_id=8),
             index_row("NP-21", s11=False, outcome="built", repo_id=8, role="reserve"),
             index_row("NP-26", s11=False, outcome="not built", repo_id=9)]
    assert pf.unprocessed_families(full) == []
    assert pf.unprocessed_families(full + open_) == ["NP-21", "NP-26"]
    no_repo = {"task_id": "NP-27", "s10": {"outcome": "not built"}}
    assert pf.unprocessed_families([no_repo]) == ["NP-27"]


def test_a_repository_s_open_places_are_counted_over_both_samples(pf):
    """§19.3: a repository with 2 accepted families builds no other, whichever samples they come from. A run's sample
    restricts the rows that need an S10 outcome, not the count of a repository's accepted families."""
    rows = [index_row("NP-04", repo_id=7), index_row("NP-23", s11=False, outcome="not built", repo_id=7, role="reserve"),
            index_row("NP-30", repo_id=7, sample="extension"),
            index_row("NP-31", s11=False, outcome="not built", repo_id=8, sample="extension"),
            index_row("NP-24", s11=False, outcome="not built", repo_id=8, role="reserve")]
    assert pf.unprocessed_families(rows, "first") == ["NP-24"]  # repository 7 is full: NP-04 and NP-30
    assert pf.unprocessed_families(rows, "extension") == ["NP-31"]
    assert pf.unprocessed_families(rows) == ["NP-24", "NP-31"]  # every row (§19.5)
    assert pf.unprocessed_families([r for r in rows if r["sample"] == "first"], "first") == ["NP-23", "NP-24"]


def test_building_stops_by_sample_for_the_two_runs(pf):
    """§20.2: natural-pr-v1 needs S9 complete for the first sample and each of its families processed, whatever the
    extension's state, and has no branch at 30 accepted; natural-pr-v2 stops at 30 accepted tasks in all (both samples),
    or once S9 is complete for the extension and each of its families has been processed."""
    first = [index_row("NP-01", repo_id=1), index_row("NP-02", s11=False, outcome="rejected", repo_id=2),
             index_row("NP-21", s11=False, outcome="not built", repo_id=2, role="reserve")]
    extension = [index_row("NP-26", s11=False, outcome="not built", repo_id=3, sample="extension")]
    s9 = {"first": {"screened": 150, "families": ["NP-01", "NP-02", "NP-21"]},
          "extension": {"screened": 534, "families": ["NP-26"]}}

    def problems(sample, rows, record=s9):
        return pf.building_problems({"tasks": rows, "s9_complete": record}, None, sample)

    reserve = "1 family of the first sample in a repository with an open place has no S10 outcome (NP-21)"
    family = "1 family of the extension in a repository with an open place has no S10 outcome (NP-26)"
    assert problems("first", first + extension) == [STOP_FIRST.format(why=reserve)]
    assert problems("extension", first + extension) == [STOP_EXTENSION.format(n=1, why=family)]
    first[2] = index_row("NP-21", s11=False, outcome="rejected", repo_id=2, role="reserve")
    assert problems("first", first + extension) == []  # the extension's family is pending: no matter for natural-pr-v1
    assert problems("first", first + extension, {"first": s9["first"]}) == []  # nor is the extension's S9 record
    assert problems("extension", first + extension, {"first": s9["first"]}) == [
        STOP_EXTENSION.format(n=1, why=f"{NO_S9.format(sample='extension', what='absent')}; {family}")]
    assert problems("first", first + extension, {"extension": s9["extension"]}) == [
        STOP_FIRST.format(why=NO_S9.format(sample="first", what="absent"))]
    assert problems(None, first + extension) == [STOP.format(n=1, why=family.replace(" of the extension in", " of"))]
    extension[0] = index_row("NP-26", s11=False, outcome="rejected", repo_id=3, sample="extension")
    assert problems("extension", first + extension) == []
    # 30 accepted tasks in all stop the extension's building (and §19.5's), not the first sample's
    many = [index_row(f"NP-{n}", repo_id=n) for n in range(50, 79)]  # 29 more accepted: 30 with NP-01
    pending = [index_row("NP-22", s11=False, outcome="not built", repo_id=2, role="reserve"),
               index_row("NP-40", s11=False, outcome="not built", repo_id=40, sample="extension")]
    rows = first + many + pending
    assert problems("extension", rows, None) == [] and problems(None, rows, None) == []
    assert problems("first", rows) == [
        STOP_FIRST.format(why="1 family of the first sample in a repository with an open place has no S10 outcome (NP-22)")]
    with pytest.raises(ValueError, match="no S9 sample 'second'"):
        pf.building_problems({"tasks": rows}, None, "second")


def test_the_s9_record_is_read_by_sample(pf):
    record = {"first": {"screened": 149, "families": ["NP-01"]}, "extension": True}
    index = {"tasks": [index_row("NP-01", repo_id=1)], "s9_complete": record}
    first = ["S9 has not screened the whole first sample (s9_complete.first.screened is 149, the sample has 150 comments)"]
    assert pf.s9_problems(index, ("first",)) == first
    assert pf.s9_problems(index, ("extension",)) == [NO_S9.format(sample="extension", what="true")]
    assert pf.s9_problems(index) == [*first, NO_S9.format(sample="extension", what="true")]


def test_a_family_that_s9_lists_for_a_sample_needs_a_row_that_names_that_sample(pf, family, capsys):
    """§20.2, failing closed: a sample's building rule reads the rows that name that sample, so a family that the S9
    record lists for it under a row that names the other sample, or neither, could be left out of the rule (or graded in
    the other run). The S9 record then does not show the sample complete, for its own rule and for §19.5's, whatever the
    family's S10 outcome; natural-pr-v1 is refused for a pending first-sample family recorded as the extension's."""
    rows = [index_row("NP-01", repo_id=1), index_row("NP-02", s11=False, outcome="not built", repo_id=2, sample="extension"),
            index_row("NP-03", s11=False, outcome="rejected", repo_id=3, sample=None)]
    index = {"tasks": rows, "s9_complete": {"first": {"screened": 150, "families": ["NP-01", "NP-02", "NP-03"]},
                                            "extension": {"screened": 534, "families": []}}}
    why = listed_elsewhere("first", "NP-02, NP-03")
    assert pf.s9_problems(index, ("first",)) == pf.s9_problems(index) == [why]
    assert pf.s9_problems(index, ("extension",)) == []
    assert pf.building_problems(index, None, "first") == [STOP_FIRST.format(why=why)]
    assert pf.building_problems(index, None) == [
        STOP.format(n=1, why=f"{why}; 1 family of a repository with an open place has no S10 outcome (NP-02)")]
    root, _ = family
    write_index(root, [index_row(), index_row("NP-91", s11=False, outcome="not built", repo_id=991, sample="extension")],
                s9={"first": {"screened": 150, "families": [TID, "NP-91"]}, "extension": S9_DONE["extension"]})
    assert run(pf, root, *RUN, capsys=capsys)[1] == [STOP_FIRST.format(why=listed_elsewhere("first", "NP-91"))]


@pytest.mark.parametrize("sample", [None, "absent", "second"])
def test_a_row_that_names_neither_sample_counts_for_both_samples(pf, sample):
    """§20.2, failing closed: a row that names neither sample may be a family of either, so for each sample's rule it
    needs an S10 outcome while its repository has an open place, and the reason says that nothing shows it is not of
    that sample. Rows of the other sample still do not count, and once the row is processed its sample does not matter
    to building (``sample_problems`` still fails a run for it)."""
    unnamed = index_row("NP-27", s11=False, outcome="not built", repo_id=27, sample=None if sample == "absent" else sample)
    if sample == "absent":
        del unnamed["sample"]
    rows = [index_row("NP-01", repo_id=1), unnamed,
            index_row("NP-28", s11=False, outcome="not built", repo_id=28, sample="extension")]
    assert pf.unprocessed_families(rows, "first") == ["NP-27"]
    assert pf.unprocessed_families(rows, "extension") == pf.unprocessed_families(rows) == ["NP-27", "NP-28"]
    index = {"tasks": rows, "s9_complete": {"first": {"screened": 150, "families": ["NP-01"]},
                                            "extension": {"screened": 534, "families": ["NP-28"]}}}
    nothing = ("1 family whose row names neither sample, in a repository with an open place, has no S10 outcome (NP-27), "
               "and nothing shows that it is not of {}")
    assert pf.building_problems(index, None, "first") == [STOP_FIRST.format(why=nothing.format("the first sample"))]
    assert pf.building_problems(index, None, "extension") == [STOP_EXTENSION.format(n=1, why=(
        "1 family of the extension in a repository with an open place has no S10 outcome (NP-28); "
        f"{nothing.format('the extension')}"))]
    unnamed["s10"] = {"outcome": "rejected", "stage": "S10"}
    assert pf.building_problems(index, None, "first") == []
    assert len(pf.sample_problems(index)) == 1


def test_the_run_and_the_label_proposer_share_the_rules_of_the_index(pf):
    """scripts/propose_labels.py applies the pre-flight's own functions before D19 (decision log D73), and
    natural_run_problems reports with them: the accepted families of a sample, every one of which the run of that sample
    grades, and the rows that name neither sample, which fail a run."""
    rows = [index_row(), index_row("NP-03", repo_id=3), index_row("NP-91", repo_id=991, sample="extension"),
            index_row("NP-92", s11=False, outcome="rejected", repo_id=992), {"task_id": "NP-93", "s11": True}]
    index = {"tasks": rows}
    assert pf.accepted_families(index, "first") == ["NP-03", TID]
    assert pf.accepted_families(index, "extension") == ["NP-91"]
    assert pf.sample_problems(index) == [
        ("natural: 1 row of the committed index (NP-93) names neither sample ('first' or 'extension'), so nothing shows "
         f"which run grades it ({TWO_RUNS})")]
    assert pf.sample_problems({"tasks": rows[:4]}) == []
    assert pf.natural_run_problems([(TID, True)], index, "natural-pr-v1") == [*pf.sample_problems(index), (
        "natural: the run leaves out accepted families of the first sample in the committed index (NP-03); the run "
        "natural-pr-v1 grades every accepted family of the first sample (protocol §20.2)")]


def test_the_preflight_fails_until_building_has_stopped(pf, family, capsys):
    root, _ = family
    write_index(root, [index_row(), index_row("NP-91", s11=False, outcome="not built", repo_id=991)], s9=None)
    pending = "1 family of the first sample in a repository with an open place has no S10 outcome (NP-91)"
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        STOP_FIRST.format(why=f"{NO_S9.format(sample='first', what='absent')}; {pending}")]
    (root / INDEX).unlink()
    _git(root, "rm", "-q", "--cached", "--", INDEX.as_posix())
    _git(root, "commit", "-q", "--no-verify", "-m", "no index")
    fails = run(pf, root, *RUN, capsys=capsys)[1]
    assert fails == [(f"natural: the committed index (data/manifests/natural_tasks_index.json in the HEAD commit) cannot be "
                      f"read ({pf.INDEX_NOT_SHOWN}), so nothing shows that building has stopped or which families are "
                      "accepted (protocol §16.4, §19.5, §20.2)")]


def test_the_committed_index_is_read_as_the_acceptance_gate_reads_it(pf, tmp_path):
    """The pre-flight reads the committed index and the correction events with the acceptance gate's own functions
    (``contract.committed_text``, ``contract.correction_event_ids``), so the two cannot drift apart; since git gives no
    reason, a directory that is no git repository is not reported as a commit without the file."""
    from tracecontract import contract

    assert pf.committed_text is contract.committed_text and pf.correction_event_ids is contract.correction_event_ids
    assert (pf.NATURAL_INDEX, pf.S10_RECORD) == (contract.NATURAL_INDEX, contract.S10_RECORD)
    assert not hasattr(pf, "correction_events")
    index, why = pf.committed_index(tmp_path)  # not a git repository
    assert index is None and why == pf.INDEX_NOT_SHOWN and "not a git repository" in why


def test_the_preflight_cites_d64_for_the_recipe_and_d71_for_the_two_runs():
    """The natural recipe's decision-log entry is D64 (planned as D61, which is the fresh-v1 run record), and the arm's two
    runs are protocol §20 (v0.12), hashed in D71: the pre-flight's natural rules cite D64 wherever they name the recipe,
    D71 only beside §20, D65 (the order record) and D73 for the phase-end log and D19's place in the run, and no other
    entry after D60. Its docstring describes the two runs, not §19.7's one run, and the phase-end requirement."""
    text = (R / "scripts" / "preflight_final_run.py").read_text(encoding="utf-8")
    assert set(re.findall(r"\bD(?:6[1-9]|[7-9]\d)\b", text)) == {"D64", "D65", "D71", "D73"}
    for m in re.finditer(r"\bD65\b", text):  # each beside the phase-end log, the order record
        assert "phase" in text[max(m.start() - 400, 0):m.end() + 200], text[m.start() - 80:m.end() + 40]
    mentions = list(re.finditer(r"\brecipe\b", text))
    assert len(mentions) >= 4  # the audit rule's text and comments, and the order of the missing audits
    for m in mentions:  # each names D64 right after the recipe
        assert "D64" in text[m.end():m.end() + 20], text[m.start() - 60:m.end() + 40]
    d71 = list(re.finditer(r"\bD71\b", text))
    assert len(d71) >= 3  # the docstring, the runs' constants and their checks
    for m in d71:  # each cites §20 right before
        assert "§20" in text[m.start() - 30:m.start()], text[m.start() - 60:m.end() + 20]
    doc = _preflight().__doc__
    assert "§20.2, decision log D71" in doc and "``natural-pr-v1``" in doc and "``natural-pr-v2``" in doc
    assert "the one run of the arm" not in doc and "does not write the record yet" not in doc
    flat = " ".join(doc.split())
    assert "the order record of decision log D65" in flat and "in order (D73; :func:`phase_end_problems`)" in flat
    assert "applies before it proposes any D19 label" not in flat  # the rule of both samples, as it was before D73


def test_the_phase_end_rule_says_what_it_reads_and_whose_reading_it_is():
    """The time condition of the order rule is the pre-flight's own reading of "in order", which D65 does not state; the
    rule reads the log as HEAD holds it, while the order of the commits that added its lines, D65's order record, stays
    the builder's record; one bad line makes the log unusable because skipping it could hide a family's repeated or
    out-of-order phase (a missing one shows anyway); and the label proposer applies the rule to every family of the run."""
    mod = _preflight()

    def flat(text: str | None) -> str:
        return " ".join((text or "").split())

    reader, rule, doc = flat(mod.committed_phase_ends.__doc__), flat(mod.phase_end_problems.__doc__), flat(mod.__doc__)
    assert "skipping it could hide a family's phase that is repeated or out of order" in reader
    assert "a family could lack a line without it showing" not in reader
    assert 'the pre-flight\'s own reading of "in order" (D65 states none)' in rule
    assert "D65's order record itself, stays the builder's record" in rule
    assert 'That time condition is the pre-flight\'s own reading of "in order"' in doc
    assert "the order of the commits that added them stays the builder's record" in doc
    assert "the family and every accepted family of its sample (:func:`accepted_families`" in doc


def test_the_run_grades_every_accepted_family_of_its_sample_and_no_other_population(pf, family, capsys):
    root, td = family
    write_index(root, [index_row(), index_row("NP-91", repo_id=991), index_row("NP-92", repo_id=992),
                       index_row("NP-93", repo_id=993, sample="extension")])  # NP-93 is natural-pr-v2's
    assert run(pf, root, *RUN, capsys=capsys)[1] == [
        ("natural: the run leaves out accepted families of the first sample in the committed index (NP-91, NP-92); the run "
         "natural-pr-v1 grades every accepted family of the first sample (protocol §20.2)")]
    write_index(root)
    other = fixture_task(root)
    fails = run(pf, root, *RUN, tasks=[td, other], capsys=capsys)[1]
    assert ("natural: the run mixes natural:pr-review tasks with tasks of other populations (FX-PF); each population gets "
            "its own run (protocol §15.2)") in fails
    assert not [f for f in fails if f.startswith(f"{TID}:")]


# --- the two runs of §20.2: natural-pr-v1 (the first sample) and natural-pr-v2 (the extension) --------------------------

def test_natural_pr_v1_does_not_wait_for_the_extension(pf, family, capsys):
    """§20.2: natural-pr-v1 grades the first sample's accepted families once building has stopped for the first sample.
    The extension's families may still be unscreened, pending or accepted (natural-pr-v2 grades those), although §19.5's
    rule over both samples has not stopped (nor does the label proposer apply that rule since D73)."""
    root, _ = family
    rows = [index_row(), index_row("NP-91", s11=False, outcome="not built", repo_id=991, sample="extension"),
            index_row("NP-92", s11=False, outcome="built", repo_id=992, role="reserve", sample="extension"),
            index_row("NP-93", repo_id=993, sample="extension")]
    for extension in ({}, {"extension": {"screened": 200, "families": ["NP-91", "NP-92", "NP-93"]}}):
        write_index(root, rows, s9={"first": S9_DONE["first"], **extension})
        assert run(pf, root, *RUN, capsys=capsys) == (0, [], [])
        index, why = pf.committed_index(root)
        assert why is None and pf.building_problems(index, why)[0].startswith(
            "natural: building has not stopped by the committed index: it counts 2 accepted task(s) of both samples")


def test_natural_pr_v1_grades_no_family_of_the_extension(pf, family, capsys):
    """NP-90 recorded as a family of the extension: natural-pr-v1 refuses it, and leaves out the first sample's accepted
    family; natural-pr-v2 grades it."""
    root, _ = family
    includes = ("natural: the run natural-pr-v1 includes families of the extension (NP-90), but it grades the accepted "
                "families of the first sample only, and natural-pr-v2 those of the extension (protocol §20.2)")
    extension = {"extension": {"screened": 534, "families": [TID]}}
    write_index(root, [index_row(sample="extension")], s9={"first": {"screened": 150, "families": []}, **extension})
    assert run(pf, root, *RUN, capsys=capsys)[1] == [includes]
    assert run(pf, root, *RUN_V2, capsys=capsys) == (0, [], [])
    write_index(root, [index_row(sample="extension"), index_row("NP-03", repo_id=3)],
                s9={"first": {"screened": 150, "families": ["NP-03"]}, **extension})
    assert run(pf, root, *RUN, capsys=capsys)[1] == [includes, (
        "natural: the run leaves out accepted families of the first sample in the committed index (NP-03); the run "
        "natural-pr-v1 grades every accepted family of the first sample (protocol §20.2)")]
    assert run(pf, root, *RUN_V2, capsys=capsys) == (0, [], [])  # NP-03 is natural-pr-v1's


def test_natural_pr_v2_waits_until_building_has_stopped_for_the_extension(pf, family, capsys):
    """NP-90 recorded as a family of the extension: natural-pr-v2 is refused while S9 is not complete for the extension
    or one of its families in a repository with an open place has no S10 outcome, and passes once every family of the
    extension has been processed, or at 30 accepted tasks in all. It grades every accepted family of the extension."""
    root, _ = family
    s9 = {"extension": {"screened": 534, "families": [TID, "NP-91"]}}  # the first sample's record is not read
    rows = [index_row(sample="extension"), index_row("NP-91", s11=False, outcome="not built", repo_id=991, sample="extension")]
    pending = "1 family of the extension in a repository with an open place has no S10 outcome (NP-91)"
    write_index(root, rows, s9=s9)
    assert run(pf, root, *RUN_V2, capsys=capsys)[1] == [STOP_EXTENSION.format(n=1, why=pending)]
    write_index(root, rows, s9={"extension": {"screened": 533, "families": [TID, "NP-91"]}})
    unscreened = ("S9 has not screened the whole extension sample (s9_complete.extension.screened is 533, the sample has 534 "
                  "comments)")
    assert run(pf, root, *RUN_V2, capsys=capsys)[1] == [STOP_EXTENSION.format(n=1, why=f"{unscreened}; {pending}")]
    # processed: rejected at S10, or in a repository with no open place (2 accepted families, one of each sample)
    for rest in ([index_row("NP-91", s11=False, outcome="rejected", repo_id=991, sample="extension")],
                 [index_row("NP-91", s11=False, outcome="not built", repo_id=990, sample="extension"),
                  index_row("NP-03", repo_id=990)]):
        write_index(root, [rows[0], *rest], s9=s9)
        assert run(pf, root, *RUN_V2, capsys=capsys) == (0, [], [])
    # 30 accepted tasks in all stop it, whatever is pending and whatever the S9 record says
    many = [index_row(f"NP-{n:02d}", repo_id=n) for n in range(1, 30)]  # 29 accepted families of the first sample
    write_index(root, [*rows, *many], s9=None)
    assert run(pf, root, *RUN_V2, capsys=capsys) == (0, [], [])
    write_index(root, [rows[0], index_row("NP-94", repo_id=994, sample="extension")],
                s9={"extension": {"screened": 534, "families": [TID, "NP-94"]}})
    assert run(pf, root, *RUN_V2, capsys=capsys)[1] == [
        ("natural: the run leaves out accepted families of the extension in the committed index (NP-94); the run "
         "natural-pr-v2 grades every accepted family of the extension (protocol §20.2)")]


def test_a_natural_run_never_mixes_the_two_samples(pf):
    """A run of a family of each sample (a run gives one task directory per family): each of the two runs refuses the
    other sample's family, and a run id that names neither run is refused for the mix too."""
    index = {"tasks": [index_row(), index_row("NP-91", repo_id=991, sample="extension")]}
    both = [(TID, True), ("NP-91", True)]
    assert pf.natural_run_problems(both, index, "natural-pr-v1") == [
        ("natural: the run natural-pr-v1 mixes the two samples: it includes families of the extension (NP-91), but it "
         "grades the accepted families of the first sample only, and natural-pr-v2 those of the extension (protocol §20.2)")]
    assert pf.natural_run_problems(both, index, "natural-pr-v2") == [
        ("natural: the run natural-pr-v2 mixes the two samples: it includes families of the first sample (NP-90), but it "
         "grades the accepted families of the extension only, and natural-pr-v1 those of the first sample (protocol §20.2)")]
    for run_id in (None, "natural-pr-v3"):  # refused for its run id too (natural_run_id_problems)
        assert pf.natural_run_problems(both, index, run_id) == [
            f"natural: the run mixes the two samples (first: NP-90; extension: NP-91); {TWO_RUNS}"]
    assert pf.natural_run_problems([(TID, True)], index, "natural-pr-v1") == []
    assert pf.natural_run_problems([("NP-91", True)], index, "natural-pr-v2") == []
    assert pf.natural_run_problems([(TID, True)], None, "natural-pr-v1") == []  # building_problems reports the index
    index["tasks"] += [index_row("NP-92", repo_id=992, sample=None), {"task_id": "NP-93", "s11": False}]
    assert pf.natural_run_problems([(TID, True)], index, "natural-pr-v1") == [
        ("natural: 2 rows of the committed index (NP-92, NP-93) name neither sample ('first' or 'extension'), so nothing "
         f"shows which run grades them ({TWO_RUNS})")]


@pytest.mark.parametrize("sample", [None, "absent", "second", ["first"]])
def test_every_row_of_the_committed_index_names_its_sample(pf, family, capsys, sample):
    """A row that names neither sample could be left out of both runs or graded by either, so it fails, whether it is
    another accepted family's (which no run would then grade) or the run's own family's."""
    root, _ = family

    def row(task_id: str = TID, repo_id: int = 990) -> dict:
        r = index_row(task_id, repo_id=repo_id, sample=None if sample == "absent" else sample)
        if sample == "absent":
            del r["sample"]
        return r

    def unknown(task_id: str) -> str:
        return (f"natural: 1 row of the committed index ({task_id}) names neither sample ('first' or 'extension'), so "
                f"nothing shows which run grades it ({TWO_RUNS})")

    write_index(root, [index_row(), row("NP-91", 991)])
    assert run(pf, root, *RUN, capsys=capsys)[1] == [unknown("NP-91")]
    write_index(root, [row()])  # S9 lists NP-90 for the first sample, whose row then does not name it either
    assert run(pf, root, *RUN, capsys=capsys)[1] == [STOP_FIRST.format(why=listed_elsewhere("first", TID)), unknown(TID)]
    assert run(pf, root, *RUN_V2, capsys=capsys)[1] == [unknown(TID)]


def test_a_run_id_that_names_neither_run_keeps_the_rule_of_both_samples(pf, family, capsys):
    """For a run id that §20.2 does not know, nothing says which sample the run grades: building is checked as §19.5 reads
    for both samples together, beside the refusal of the run id."""
    root, _ = family
    write_index(root, [index_row(), index_row("NP-91", s11=False, outcome="not built", repo_id=991, sample="extension")],
                s9={"first": S9_DONE["first"], "extension": {"screened": 534, "families": ["NP-91"]}})
    stop = STOP.format(n=1, why="1 family of a repository with an open place has no S10 outcome (NP-91)")
    assert run(pf, root, *OPTIONS, capsys=capsys)[1] == [stop, (
        f"natural: pass --run-id natural-pr-v1 or natural-pr-v2 here and to evaluate: {TWO_RUNS}, and the pre-flight checks "
        "that the run has not been made")]
    assert run(pf, root, "--run-id", "natural-pr-v3", *OPTIONS, capsys=capsys)[1] == [
        stop, f"natural: the run id is 'natural-pr-v3'; {TWO_RUNS}"]
    assert run(pf, root, *RUN, capsys=capsys) == (0, [], [])


# --- the phase ends of every natural family the run grades (D65, D73) ---------------------------------------------------

PHASE_LOG = "the committed phase-end log (data/manifests/natural_phase_ends.jsonl in the HEAD commit)"


def no_line(tid: str, which: str) -> str:
    return (f"{tid}: {PHASE_LOG} has no line for its {which}; D19 and the run grade a natural family once its phases P1 to "
            "P7 have ended, each recorded with scripts/record_phase_end.py and committed (decision log D65, D73)")


def not_in_order(tid: str, lines: list[dict]) -> str:
    shown = ", ".join(f"{x['phase']} at {x['recorded_at']}" for x in lines)
    return (f"{tid}: its lines in {PHASE_LOG} are not in the order of its phases ({shown}); in order, each phase comes "
            "once, after the phase before it, and is recorded no earlier than it (the pre-flight's reading of decision log "
            "D73; scripts/record_phase_end.py refuses to append a line that breaks it, D65)")


def unreadable(why: str, tids: str = TID) -> str:
    return (f"natural: {PHASE_LOG} cannot be read ({why}), so nothing shows that {tids} ended the phases P1 to P7 in order; "
            "D19 and the run of a natural family need them (decision log D65, D73)")


def log_repo(root: Path, lines: list | None = None) -> Path:
    """A git repository at ``root`` whose HEAD commit holds the phase-end log ``lines`` (None: it has no commit)."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True, env=_git_env())
    if lines is not None:
        write_phase_ends(root, lines)
    return root


def test_a_natural_run_needs_the_family_s_phases_p1_to_p7(pf, family, capsys):
    """D73: the pre-flight requires, for every family of a natural run, the lines of its phases P1 to P7 in the committed
    phase-end log (the order record of D65), in order: a family that lacks P7, or whose P5 comes after its P4 has not,
    fails; once its seven lines are committed in order, the run passes."""
    root, _ = family
    write_phase_ends(root, phase_ends(TID, PHASES[:6]))
    assert run(pf, root, *RUN, capsys=capsys)[1] == [no_line(TID, "phase P7")]
    swapped = phase_ends(TID, ("P1", "P2", "P3", "P5", "P4", "P6", "P7"))
    write_phase_ends(root, swapped)
    assert run(pf, root, *RUN, capsys=capsys)[1] == [not_in_order(TID, swapped)]
    write_phase_ends(root, phase_ends(TID))
    assert run(pf, root, *RUN, capsys=capsys) == (0, [], [])


def test_each_family_needs_its_own_lines_in_order(pf, tmp_path):
    """Family by family, in task-id order, each once: lines of other tasks do not count, another family's lines between a
    family's own do not break its order, and a phase recorded twice, after a later one, or at an earlier time than the
    phase before it is out of order. A family with no line lacks all seven."""
    swapped = ("P1", "P3", "P2", *PHASES[3:])
    twice = ("P1", "P2", "P2", *PHASES[2:])
    early = phase_ends("NP-05")
    early[6]["recorded_at"] = "2026-11-22T05:59:59Z"  # P7 recorded before P6 (06:00), though after it in the log
    side_by_side = [x for pair in zip(phase_ends(TID), phase_ends("NP-92", day="2026-11-21"), strict=True) for x in pair]
    root = log_repo(tmp_path, [*phase_ends("NP-91", PHASES[:6]), *side_by_side, *phase_ends("NP-03", swapped),
                               *phase_ends("NP-04", twice), *early])
    assert pf.phase_end_problems(root, ["NP-91", TID, "NP-03", "NP-04", "NP-05", TID, "NP-92"]) == [
        not_in_order("NP-03", phase_ends("NP-03", swapped)), not_in_order("NP-04", phase_ends("NP-04", twice)),
        not_in_order("NP-05", early), no_line("NP-91", "phase P7")]
    assert pf.phase_end_problems(root, ["NP-93"]) == [no_line("NP-93", "phases P1, P2, P3, P4, P5, P6, P7")]
    assert pf.phase_end_problems(root, [TID, "NP-92"]) == [] and pf.phase_end_problems(root, []) == []


def test_main_checks_the_phase_ends_of_every_natural_family_it_grades(pf, family, monkeypatch, capsys):
    """main gives the rule the natural families of the run, and no task of another population, with its repository."""
    root, td = family
    seen = []
    real = pf.phase_end_problems
    monkeypatch.setattr(pf, "phase_end_problems", lambda repo, ids: seen.append((repo, list(ids))) or real(repo, ids))
    run(pf, root, *RUN, tasks=[fixture_task(root), td], capsys=capsys)
    assert seen == [(root, [TID])]


def test_the_phase_end_log_is_read_from_the_head_commit_only(pf, family, monkeypatch, tmp_path_factory, capsys):
    """As the committed index is read (contract.committed_text): the working tree's log, which record_phase_end.py appends
    to before the builder commits it, is not read, and GIT_DIR or GIT_WORK_TREE of the caller (a hook's, say) does not
    redirect git to another repository."""
    root, _ = family
    write_phase_ends(root, phase_ends(TID, PHASES[:6]))  # committed without P7
    write_phase_ends(root, phase_ends(TID), commit=False)  # P7 in the working tree only
    assert run(pf, root, *RUN, capsys=capsys)[1] == [no_line(TID, "phase P7")]
    other = log_repo(tmp_path_factory.mktemp("other"), phase_ends(TID))  # its HEAD commit holds the whole log
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    records, why = pf.committed_phase_ends(root)
    assert why is None and [r["phase"] for r in records] == list(PHASES[:6])
    assert pf.phase_end_problems(root, [TID]) == [no_line(TID, "phase P7")]
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    write_phase_ends(root, phase_ends(TID))  # P7 committed
    (root / PHASE_ENDS).write_text("not a phase-end log\n", encoding="utf-8")  # the working tree's log, not read
    assert run(pf, root, *RUN, capsys=capsys) == (0, [], [])


LINE = phase_end_line(TID, "P1", "2026-11-22T01:00:00Z")


@pytest.mark.parametrize("bad, why", [
    ("{not json", "its line 2 is not JSON"),
    (json.dumps([TID, "P1"]), "its line 2 is not a JSON object"),
    (json.dumps("P1"), "its line 2 is not a JSON object"),
    (json.dumps({k: v for k, v in LINE.items() if k != "schema"}),
     f"its line 2 is not a record of {PHASE_END_SCHEMA} (its schema is null)"),
    (json.dumps({**LINE, "schema": "tracecontract/natural-phase-end/v2"}),
     f'its line 2 is not a record of {PHASE_END_SCHEMA} (its schema is "tracecontract/natural-phase-end/v2")'),
    (json.dumps({**LINE, "task_id": ""}), 'its line 2 names no task (its task_id is "")'),
    (json.dumps({**LINE, "task_id": 90}), "its line 2 names no task (its task_id is 90)"),
    (json.dumps({**LINE, "phase": "p1"}), 'its line 2 records the phase "p1", not one of P1, P2, P3, P4, P5, P6, P7'),
    (json.dumps({**LINE, "phase": None}), "its line 2 records the phase null, not one of P1, P2, P3, P4, P5, P6, P7"),
    (json.dumps({k: v for k, v in LINE.items() if k != "recorded_at"}),
     "its line 2 records no time with a time zone (its recorded_at is null)"),
    (json.dumps({**LINE, "recorded_at": 5}), "its line 2 records no time with a time zone (its recorded_at is 5)"),
    (json.dumps({**LINE, "recorded_at": "yesterday"}),
     'its line 2 records no time with a time zone (its recorded_at is "yesterday")'),
    (json.dumps({**LINE, "recorded_at": "2026-11-22T01:00:00"}),
     'its line 2 records no time with a time zone (its recorded_at is "2026-11-22T01:00:00")'),
])
def test_a_line_that_is_not_a_phase_end_record_makes_the_log_unusable(pf, tmp_path, bad, why):
    """Fail closed: one line of any task that is not a record of tracecontract/natural-phase-end/v1 (a JSON object with
    that schema, a task id, a phase P1 to P7 and a time with a time zone) shows nothing for any family."""
    root = log_repo(tmp_path, [phase_end_line("NP-91", "P1", "2026-11-22T00:30:00Z"), bad, *phase_ends(TID)])
    assert pf.committed_phase_ends(root) == (None, why)
    assert pf.phase_end_problems(root, [TID, "NP-03"]) == [unreadable(why, "NP-03, NP-90")]


def test_a_log_that_git_does_not_give_from_the_head_commit_is_unusable(pf, tmp_path):
    """No repository, no commit, a HEAD commit without the log, or a log that is not UTF-8: git gives no text, and the
    reason names every case (contract.committed_text does not say which)."""
    none = (None, pf.INDEX_NOT_SHOWN)
    assert pf.committed_phase_ends(tmp_path / "nowhere") == none  # not even a directory
    (tmp_path / "plain").mkdir()
    assert pf.committed_phase_ends(tmp_path / "plain") == none  # not a git repository
    empty = log_repo(tmp_path / "empty")
    assert pf.committed_phase_ends(empty) == none  # no commit
    elsewhere = log_repo(tmp_path / "elsewhere")
    (elsewhere / "README").write_text("synthetic\n", encoding="utf-8")
    commit_file(elsewhere, Path("README"), "a commit without the log (synthetic fixture)")
    write_phase_ends(elsewhere, phase_ends(TID), commit=False)  # in the working tree only
    assert pf.committed_phase_ends(elsewhere) == none
    latin = log_repo(tmp_path / "latin", phase_ends(TID))
    (latin / PHASE_ENDS).write_bytes(b'{"note": "caf\xe9"}\n')
    commit_file(latin, PHASE_ENDS, "a log that is not UTF-8 (synthetic fixture)")
    assert pf.committed_phase_ends(latin) == none
    assert pf.phase_end_problems(latin, [TID]) == [unreadable(pf.INDEX_NOT_SHOWN)]


def test_the_log_is_split_at_line_feeds_and_blank_lines_are_skipped(pf, tmp_path):
    """store.jsonl_lines: a record whose string holds U+2028 stays whole (str.splitlines would cut it in two), a CRLF line
    end is read, and a blank line is skipped but counted, so the line numbers of the reasons are the file's."""
    lines = phase_ends(TID)
    lines[2] = json.dumps({**lines[2], "note": "one two"}, ensure_ascii=False)  # a raw U+2028 in a string
    lines[3] = json.dumps(lines[3]) + "\r"
    root = log_repo(tmp_path, [lines[0], "", *lines[1:]])
    records, why = pf.committed_phase_ends(root)
    assert why is None and [r["phase"] for r in records] == list(PHASES) and records[2]["note"] == "one two"
    assert pf.phase_end_problems(root, [TID]) == []
    write_phase_ends(root, [lines[0], "", "   ", "{not json"])
    assert pf.committed_phase_ends(root) == (None, "its line 4 is not JSON")


def test_a_log_that_cannot_be_used_fails_the_run_once(pf, family, capsys):
    """A run of natural families gets one failure for a log that cannot be used, whatever its families."""
    root, _ = family
    write_phase_ends(root, [*phase_ends(TID), "{not json"])
    assert run(pf, root, *RUN, capsys=capsys)[1] == [unreadable("its line 8 is not JSON")]
    _git(root, "rm", "-q", "--", PHASE_ENDS.as_posix())
    _git(root, "commit", "-q", "--no-verify", "-m", "no phase-end log (synthetic fixture)")
    assert run(pf, root, *RUN, capsys=capsys)[1] == [unreadable(pf.INDEX_NOT_SHOWN)]


def test_the_log_that_record_phase_end_writes_is_read_as_written(pf, family, capsys):
    """The pre-flight keeps its own copy of the log's path, schema and phases (it does not import the script), equal to
    the script's and to the test layout's; and the lines that the script appends, once committed, are read as written."""
    spec = importlib.util.spec_from_file_location("preflight_test_record_phase_end", R / "scripts" / "record_phase_end.py")
    rpe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rpe)
    assert (pf.PHASE_ENDS, pf.PHASE_END_SCHEMA, pf.NATURAL_PHASES) == (
        rpe.LOG.relative_to(rpe.R).as_posix(), rpe.SCHEMA, rpe.PHASES) == (PHASE_ENDS.as_posix(), PHASE_END_SCHEMA, PHASES)
    root, td = family
    log = root / PHASE_ENDS
    log.unlink()  # the fixture's own lines: the script writes the log from P1
    for n, phase in enumerate(PHASES):
        if n == len(PHASES) - 1:
            assert run(pf, root, *RUN, capsys=capsys)[1] == [no_line(TID, "phase P7")]
        rpe.append(td, phase, log, now=f"2026-11-22T{11 + n:02d}:00:00Z", repo=root)
        commit_file(root, PHASE_ENDS, f"phase end {phase} (synthetic fixture)")
        records, why = pf.committed_phase_ends(root)
        assert why is None and [(r["task_id"], r["phase"]) for r in records] == [(TID, p) for p in PHASES[:n + 1]]
    assert run(pf, root, *RUN, capsys=capsys) == (0, [], [])


# --- controlled tasks are not affected ---------------------------------------------------------------------------------

def test_a_controlled_run_never_reads_the_natural_index(pf, monkeypatch, capsys):
    """The four pilot tasks: the natural checks are not entered (the documented pilot command passes, as in
    tests/test_preflight_run_rules.py, without asking for the committed natural index)."""
    from tracecontract.tasks import verify_snapshot

    tasks = [R / "tasks" / t for t in ("CS-01", "CS-02", "CS-03", "CS-04")]
    if not all((R / "snapshots" / td.name).is_dir() and verify_snapshot(td, R / "snapshots") for td in tasks):
        pytest.skip("a base snapshot is missing or stale (tracecontract snapshot tasks/<id>)")

    def refuse(*_a, **_k):
        raise AssertionError("a controlled run read the natural index or the phase-end log")

    for name in ("committed_index", "committed_phase_ends", "phase_end_problems"):
        monkeypatch.setattr(pf, name, refuse)
    argv = [*map(str, tasks), "--run-id", "preflight-test-run", "--conditions", "initial_plain", "initial_audited",
            "full_plain", "full_audited", "llm_freeform", "repo_tests", "--repeats", "3", "--pilot"]
    assert pf.main(*argv) == 0, _lines(capsys.readouterr().out, "FAIL")
    out = capsys.readouterr().out
    assert "natural" not in out and not _lines(out, "NOTE")


def test_a_run_without_a_natural_task_never_reads_the_natural_records(pf, tmp_path, monkeypatch, capsys):
    """A run of a synthetic task of another population (FX-PF), also one that grades a stratum, as a fresh-v1 run does:
    the natural checks of main are not entered, so neither the natural index nor the phase-end log is read, and no
    failure names them. Needs no base snapshot of the pilot tasks."""
    other = fixture_task(tmp_path)

    def refuse(*_a, **_k):
        raise AssertionError("a run without a natural task read a natural record")

    for name in ("committed_index", "committed_phase_ends", "phase_end_problems", "building_problems"):
        monkeypatch.setattr(pf, name, refuse)
    for extra in ([], ["--strata", "fresh-v1"]):
        code, fails, _ = run(pf, tmp_path, "--run-id", "fx-run", "--repeats", "3", *extra, tasks=[other], capsys=capsys)
        assert code == 1 and fails  # the fixture task is incomplete
        assert not [f for f in fails if re.search(r"natural|phase", f)], fails


# --- the recorded natural families (read only) --------------------------------------------------------------------------

ACCEPTED = ("NP-03", "NP-04", "NP-05", "NP-18", "NP-19", "NP-20")


def test_the_recorded_accepted_families_pass_the_s10_s11_and_source_evidence_checks(pf):
    """Read only: the six accepted families of the first sample (D59) passed S10, are S11 in the committed index, resolve
    their base under data/natural/snapshots and label their pre-review state with the source evidence."""
    tds = [roots.NATURAL_TASKS / t for t in ACCEPTED]
    if not all((td / "task.json").is_file() for td in tds):
        pytest.skip("the natural tasks are not in this checkout (data/natural/ is git-ignored)")
    index, why = pf.committed_index(R)
    if index is None or not set(ACCEPTED) <= set(pf.index_rows(index)):
        pytest.skip(f"the committed index does not list the six families ({why})")
    for td in tds:
        m = load(td / "task.json", TaskManifest)
        assert m.population == Population.natural_pr_review
        assert pf.natural_record_problems(td, m, index) == [], td.name
        assert pf.roots.snapshot_root(td, repo=R) == roots.NATURAL_SNAPSHOTS.resolve()
        held = [load(td / p, Candidate) for p in m.candidates]
        held = [c for c in held if c.split == Split.eval and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]
        assert pf.source_evidence_problems(m, held) == [], td.name


def test_the_committed_index_lets_natural_pr_v1_grade_the_six_families(pf):
    """Read only (the committed index is tracked): building has stopped for the first sample (§20.2: S9 complete for it,
    and each of its families and reserves processed), its accepted families are the six of D59, and a run natural-pr-v1 of
    the six leaves none out and takes nothing of the extension."""
    index, why = pf.committed_index(R)
    if index is None:
        pytest.skip(f"the committed index cannot be read ({why})")
    assert pf.building_problems(index, why, "first") == []
    rows = pf.index_rows(index)
    assert sorted(t for t, r in rows.items() if r.get("s11") is True and pf.row_sample(r) == "first") == list(ACCEPTED)
    assert pf.natural_run_problems([(t, True) for t in ACCEPTED], index, "natural-pr-v1") == []
