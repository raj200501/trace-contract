"""The natural export of ``scripts/export_prompts.py`` (``--natural``; build plan WP-H): the natural guard withholds a
prompt that holds what the pre-push scan reports there (an AIDev login, a window or short text of a natural thread or of
a screened comment, a natural repository's name, a natural task's check id or a line of its base snapshot, an
@handle); a withheld record names the kind of finding only; natural prompts go to
``experiments/prompts/natural/agent_prompts_natural.jsonl``, where an export in batches keeps the earlier batches'
records; workflow arguments are exported; the first export's ``agent_prompts.jsonl`` is never rewritten.

A synthetic session directory (workflow run records and agent transcripts), a synthetic natural task
(tests/natural_task_layout.py) and a synthetic screening text file; the planted login, handle and e-mail address are
synthetic ones (the address is built at run time, so that this file holds none the scan would report). Not research
evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from natural_task_layout import B1_CHECKS, COMMENT_TEXT, REPLY_TEXT, build_natural_task

ROOT = Path(__file__).resolve().parents[1]
LOGIN = "fx-natural-reviewer"  # a synthetic login, given to the guard as an AIDev login
CLEAN = "Write 6 to 14 tests for the add function. Your workspace: /home/user/nat_ws/NP-90/testgen-full."
WORKFLOW = "tracecontract-natural-fixture"
RUN = "wf_fx0natural-1"
# The natural workflows' own privacy rule, which names the forms it forbids.
RULE = "// natural agents: no logins, @handles or e-mail addresses; never @mention anyone\n"
SCRIPT = f"export const meta = {{ name: '{WORKFLOW}' }};\n{RULE}"
SCREENED = ("The retry loop in the uploader swallows the timeout error, so the job reports success while nothing was "
            "stored; please surface the error to the caller instead.")  # a sampled comment that was never built
MAIL = "fx-upstream-author" + "@" + "mail-fixture.io"  # built at run time (a domain that is not reserved)
# NP-95's review comment and reply, in the shapes of two accepted families' correction comments (synthetic): 21
# characters and 3 words, 37 characters and 5 words.
SHORT_21 = "Don't mutate defaults"
SHORT_37 = 'Swap "thumbnails" for naïve previews.'
BASE_LINE = "    return fx_render_gallery(widget_cache, zoom_level=zoom)"  # a line of NP-90's base snapshot only


def _short_text_task(tasks_root: Path) -> None:
    td = tasks_root / "NP-95"
    td.mkdir(parents=True)
    events = [("review/1", SHORT_21), ("reply/1", SHORT_37)]
    (td / "session.json").write_text(json.dumps({"session_id": "s95", "population": "natural:pr-review", "events": [
        {"event_id": f"s95/{e}", "author": "human", "text": t} for e, t in events]}, ensure_ascii=False), encoding="utf-8")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ep = _load("export_prompts")
scan = _load("scan_tracked_files")


def _transcript(path: Path, prompt: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "user", "message": {"role": "user", "content": prompt}, "timestamp": "2026-11-21T10:00:00Z"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}, "timestamp": "2026-11-21T10:05:00Z"}]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


PROMPTS = {  # agent id -> prompt, and the kind of finding that withholds it (None: exported)
    "aclean": (CLEAN, None),
    "alogin": (f"Read the notes; the reviewer {LOGIN} asked for it. {CLEAN}", "AIDev login"),
    "awindow": (f"The reviewer wrote: {COMMENT_TEXT}\n{CLEAN}", "natural text window (NP-90)"),
    "aname": (f"The package is fxnat. {CLEAN}", "natural repository name (NP-90)"),
    "ahandle": (f"Thank @fx-someone for the review. {CLEAN}", "handle"),
    "ashort": (f'The reviewer then replied: "{REPLY_TEXT}" {CLEAN}', "natural short text (NP-90)"),
    "acheck": (f"B1 failed on {B1_CHECKS[1]}. {CLEAN}", "check id of a natural task (NP-90)"),
    "ascreened": (f"Judge this comment:\n{SCREENED}\n{CLEAN}", "natural text window (screened comment 501)"),
    "amail": (f"The upstream author ({MAIL}) wrote the test. {CLEAN}", None),
    "ashort21": (f"The reviewer asked: {SHORT_21}. {CLEAN}", "natural short text (NP-95)"),
    "ashort37": (f"The reply: {SHORT_37.upper()} {CLEAN}", "natural short text (NP-95)"),
    "abase": (f"The function reads:\n{BASE_LINE}\n{CLEAN}", "code line of a natural task's base snapshot (NP-90)"),
}


@pytest.fixture
def session(tmp_path: Path) -> Path:
    sd = tmp_path / "session"
    (sd / "workflows").mkdir(parents=True)
    records = [
        {"runId": RUN, "workflowName": WORKFLOW, "script": SCRIPT,
         "args": {"task": "NP-90", "ws_root": "/home/user/nat_ws/NP-90"}, "startTime": 1763719200000,
         "timestamp": "2026-11-21T10:30:00.000Z", "status": "completed"},
        {"runId": "wf_fx0natural-2", "workflowName": WORKFLOW, "script": f"// second run, mail {MAIL}\n",
         "args": {"task": "NP-90", "context": COMMENT_TEXT}, "status": "completed"},  # its arguments hold thread text
        {"runId": "wf_fx0other-1", "workflowName": "tracecontract-other", "script": "// not natural\n", "args": {}},
    ]
    for r in records:
        (sd / "workflows" / f"{r['runId']}.json").write_text(json.dumps(r), encoding="utf-8")
    agents = sd / "subagents" / "workflows" / RUN
    for aid, (prompt, _) in PROMPTS.items():
        _transcript(agents / f"agent-{aid}.jsonl", prompt)
    _transcript(sd / "subagents" / "workflows" / "wf_fx0other-1" / "agent-aother.jsonl", CLEAN)
    _transcript(sd / "subagents" / "agent-bstandalone.jsonl", CLEAN)
    _transcript(sd / "subagents" / "agent-bunlisted.jsonl", CLEAN)
    return sd


@pytest.fixture
def screening(tmp_path: Path) -> tuple[Path, list[Path]]:
    """The screening texts of one sampled comment that was never built, and the two manifests that sample it."""
    out = tmp_path / "outside"
    out.mkdir()
    texts = out / "texts.jsonl"
    texts.write_text(json.dumps({"comment_id": 501, "comment_body": SCREENED, "issue_title": "Uploads hang",
                                 "issue_body": "", "pr_title": "Retry uploads", "diff_hunk": "@@ -1 +1 @@\n-a\n+b\n"}) + "\n")
    (out / "s9.json").write_text(json.dumps({"sample": {"rows": [{"comment_id": 501}]}}))
    (out / "s9x.json").write_text(json.dumps({"rows": []}))
    return texts, [out / "s9.json", out / "s9x.json"]


@pytest.fixture
def check(tmp_path: Path, screening):
    nt = build_natural_task(tmp_path / "repo", index=False)
    (nt.snapshot_dir / "fxnat" / "render.py").write_text(f"def render(widget_cache, zoom):\n{BASE_LINE}\n", encoding="utf-8")
    _short_text_task(nt.tasks_root)
    texts, manifests = screening
    natural = scan.natural_material(nt.tasks_root, [texts], manifests=manifests)
    return ep.scan_check(scan, natural, scan.login_patterns([LOGIN]))


@pytest.fixture
def prompts(tmp_path: Path, monkeypatch) -> Path:
    """A copy of experiments/prompts' first export (agent_prompts.jsonl, README.md, a workflow script) as OUT."""
    out = tmp_path / "prompts"
    (out / "workflows").mkdir(parents=True)
    (out / "agent_prompts.jsonl").write_bytes((ROOT / "experiments" / "prompts" / "agent_prompts.jsonl").read_bytes())
    (out / "README.md").write_bytes((ROOT / "experiments" / "prompts" / "README.md").read_bytes())
    (out / "workflows" / "x__wf_1.js").write_text("// first export\n", encoding="utf-8")
    monkeypatch.setattr(ep, "OUT", out)
    monkeypatch.setattr(ep, "_REDACTIONS", list(ep._REDACTIONS))
    monkeypatch.setattr(ep, "_FORBIDDEN", list(ep._FORBIDDEN))
    return out


def _digests(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_guard_withholds_and_the_first_export_stays_byte_identical(session, check, prompts):
    real = ROOT / "experiments" / "prompts" / "agent_prompts.jsonl"
    real_before = hashlib.sha256(real.read_bytes()).hexdigest()
    before = _digests(prompts)
    counts = ep.export_natural(session, workflows=["tracecontract-natural-*"], agents=["bstandalone"], check=check)
    assert {k: v for k, v in _digests(prompts).items() if k in before} == before  # nothing of the first export changed
    assert hashlib.sha256(real.read_bytes()).hexdigest() == real_before
    nat = prompts / "natural"
    assert sorted(p.relative_to(nat).as_posix() for p in nat.rglob("*") if p.is_file()) == [
        "agent_prompts_natural.jsonl", f"workflows/{WORKFLOW}__{RUN}.args.json", f"workflows/{WORKFLOW}__{RUN}.js",
        f"workflows/{WORKFLOW}__wf_fx0natural-2.args.json", f"workflows/{WORKFLOW}__wf_fx0natural-2.js"]
    text = (nat / "agent_prompts_natural.jsonl").read_text(encoding="utf-8")
    rows = {r["agent_id"]: r for r in map(json.loads, text.splitlines())}
    assert sorted(rows) == sorted([*PROMPTS, "bstandalone"])  # not the other workflow's agent
    withheld = [aid for aid, (_, kind) in PROMPTS.items() if kind]
    assert counts == {"workflows": 2, "agents": len(PROMPTS) + 1, "withheld": len(withheld) + 1, "kept": 0}
    assert rows["aclean"]["prompt"] == CLEAN and rows["aclean"]["workflow_run"] == RUN
    assert rows["aclean"]["prompt_sha256"] == hashlib.sha256(CLEAN.encode()).hexdigest()
    assert rows["bstandalone"]["workflow_run"] is None and rows["bstandalone"]["prompt"] == CLEAN
    for aid in withheld:
        r, kind = rows[aid], PROMPTS[aid][1]
        assert r["prompt"] is None and r["prompt_sha256"] is None, aid
        assert r["withheld"] == f"withheld: it holds what scripts/scan_tracked_files.py reports there ({kind})", aid
        assert len(r["transcript_sha256"]) == 64
    for secret in (LOGIN, "fxnat", "fx-someone", COMMENT_TEXT[10:40], REPLY_TEXT[:20], SCREENED[:30], B1_CHECKS[1], MAIL,
                   SHORT_21, "mutate defaults", "THUMBNAILS", "fx_render_gallery"):
        assert secret not in text, secret
    assert "@" not in text.replace("[EMAIL REDACTED]", "") and "#" not in text  # no handle form, no login's number
    # A prompt that a generic rule changed (an upstream author's address) is exported without the hash of its original.
    assert "[EMAIL REDACTED]" in rows["amail"]["prompt"] and rows["amail"]["prompt_sha256"] is None
    # The workflow's arguments are exported; those that hold thread text are withheld.
    args = json.loads((nat / "workflows" / f"{WORKFLOW}__{RUN}.args.json").read_text(encoding="utf-8"))
    assert args == {"task": "NP-90", "ws_root": "/home/user/nat_ws/NP-90"}
    held = json.loads((nat / "workflows" / f"{WORKFLOW}__wf_fx0natural-2.args.json").read_text(encoding="utf-8"))
    assert held["args"] is None and "natural text window (NP-90)" in held["withheld"]
    # The script with the workflows' own privacy rule (its words "@handles", "@mention") is exported, with its hash.
    js = (nat / "workflows" / f"{WORKFLOW}__{RUN}.js").read_text(encoding="utf-8")
    assert js.endswith(RULE) and f"arguments in {WORKFLOW}__{RUN}.args.json" in js
    assert hashlib.sha256(SCRIPT.encode()).hexdigest() in js
    second = (nat / "workflows" / f"{WORKFLOW}__wf_fx0natural-2.js").read_text(encoding="utf-8")
    assert "sha256 of the original script: withheld (a redaction changed it)" in second and MAIL not in second
    # What the export wrote passes the scan at its place.
    for p in nat.rglob("*"):
        if p.is_file():
            assert check(ep._where(nat, p), p.read_text(encoding="utf-8")) == [], p.name


def test_withheld_records_name_the_kind_only():
    assert ep.finding_kind("aidev login #37") == "AIDev login"
    assert ep.finding_kind("@handle") == "handle"
    assert ep.finding_kind("e-mail address (sha256 0123456789abcdef)") == "e-mail address"
    assert ep.finding_kind("private marker #2") == "private marker"
    assert ep.finding_kind("natural text window (NP-03)") == "natural text window (NP-03)"
    reason = ep._withheld(["aidev login #3", "@handle", "aidev login #9", "e-mail address (sha256 ab)"])
    assert reason == "withheld: it holds what scripts/scan_tracked_files.py reports there (AIDev login; e-mail address; handle)"


def test_an_exported_handle_finding_does_not_abort_the_export(session, check, prompts):
    """A withheld @handle prompt and the workflows' privacy rule leave the finished files clean, so the export is
    written (the final re-scan used to read the reason "(@handle)" as a handle)."""
    counts = ep.export_natural(session, workflows=[RUN], agents=[], check=check)
    assert counts["withheld"] == sum(1 for _, kind in PROMPTS.values() if kind)
    row = next(json.loads(x) for x in (prompts / "natural" / ep.NATURAL_PROMPTS).read_text().splitlines()
               if json.loads(x)["agent_id"] == "ahandle")
    assert row["withheld"].endswith("(handle)")


def test_an_export_in_batches_keeps_the_earlier_records(session, check, prompts):
    """Exporting runs one batch at a time keeps the agent records of the earlier batches beside their workflow files;
    an agent exported again has its record replaced, not doubled. An earlier record file that cannot be read stops the
    export, writing nothing."""
    second = session / "subagents" / "workflows" / "wf_fx0natural-2"
    _transcript(second / "agent-b1.jsonl", CLEAN)
    first = ep.export_natural(session, workflows=[RUN], agents=[], check=check)
    assert first["kept"] == 0
    counts = ep.export_natural(session, workflows=["wf_fx0natural-2"], agents=[], check=check)
    assert counts["agents"] == 1 and counts["kept"] == first["agents"]
    nat = prompts / "natural"
    rows = [json.loads(x) for x in (nat / ep.NATURAL_PROMPTS).read_text(encoding="utf-8").splitlines()]
    assert sorted(r["agent_id"] for r in rows) == sorted([*PROMPTS, "b1"])
    assert {r["workflow_run"] for r in rows} == {RUN, "wf_fx0natural-2"}
    assert (nat / "workflows" / f"{WORKFLOW}__{RUN}.js").is_file()
    _transcript(second / "agent-b1.jsonl", f"{CLEAN} Then run the tests.")
    again = ep.export_natural(session, workflows=["wf_fx0natural-2"], agents=[], check=check)
    rows = [json.loads(x) for x in (nat / ep.NATURAL_PROMPTS).read_text(encoding="utf-8").splitlines()]
    assert again["kept"] == first["agents"] and len(rows) == len(PROMPTS) + 1
    assert [r["prompt"] for r in rows if r["agent_id"] == "b1"] == [f"{CLEAN} Then run the tests."]
    before = _digests(nat)
    (nat / ep.NATURAL_PROMPTS).write_text(json.dumps({"no_agent_id": 1}) + "\n", encoding="utf-8")
    before[ep.NATURAL_PROMPTS] = _digests(nat)[ep.NATURAL_PROMPTS]
    with pytest.raises(SystemExit, match="is not an agent record of an earlier export; nothing written"):
        ep.export_natural(session, workflows=[RUN], agents=[], check=check)
    assert _digests(nat) == before


def test_nothing_is_written_when_a_finished_file_would_be_reported(session, prompts, monkeypatch):
    calls: list[str] = []

    def check(where: str, text: str) -> list[str]:  # passes every text, then reports the finished prompts file
        calls.append(where)
        return ["@handle"] if where.endswith("agent_prompts_natural.jsonl") and "\n" in text else []

    with pytest.raises(SystemExit, match="nothing written"):
        ep.export_natural(session, workflows=[RUN], agents=[], check=check)
    assert not (prompts / "natural").exists()
    assert "experiments/prompts/natural/agent_prompts_natural.jsonl" in calls


def test_cli_requires_the_guard_inputs_and_a_selection(session, prompts, tmp_path, screening):
    texts, _ = screening
    redactions = tmp_path / "private.json"
    redactions.write_text(json.dumps({"patterns": [], "forbidden": []}), encoding="utf-8")
    base = [str(session), "--private-redactions", str(redactions), "--natural", "--natural-texts", str(tmp_path)]
    with pytest.raises(SystemExit):  # no --aidev-logins: the guard cannot run
        ep.main(*base, "--screening-texts", str(texts))
    with pytest.raises(SystemExit):  # no --screening-texts: the sampled comments that were never built are not covered
        ep.main(*base, "--aidev-logins", str(tmp_path))
    with pytest.raises(SystemExit, match="--workflow"):
        ep.main(*base, "--aidev-logins", str(tmp_path), "--screening-texts", str(texts))
    with pytest.raises(SystemExit, match="no standalone agent"):
        ep.export_natural(session, workflows=[], agents=["nosuch"], check=lambda w, t: [])
    assert not (prompts / "natural").exists()
    assert (prompts / "agent_prompts.jsonl").read_bytes() == (ROOT / "experiments/prompts/agent_prompts.jsonl").read_bytes()


def test_cli_exports_a_natural_workflow_run_and_fails_closed_without_logins(session, prompts, tmp_path, screening,
                                                                            monkeypatch):
    """The command line exports a synthetic natural workflow run whose script names the forms it forbids ("@handles",
    "@mention") and one of whose prompts is withheld for an @handle; it refuses, writing nothing, when the AIDev files
    give no login, since the login check would then be off."""
    texts, manifests = screening
    nt = build_natural_task(tmp_path / "repo", index=False)
    redactions = tmp_path / "private.json"
    redactions.write_text(json.dumps({"patterns": [], "forbidden": []}), encoding="utf-8")
    monkeypatch.setattr(ep, "_scan_module", lambda: scan)
    monkeypatch.setattr(scan, "SCREENING_MANIFESTS", tuple(manifests))
    argv = [str(session), "--private-redactions", str(redactions), "--natural", "--natural-texts", str(nt.tasks_root),
            "--screening-texts", str(texts), "--aidev-logins", str(tmp_path / "aidev"), "--workflow", RUN]
    monkeypatch.setattr(scan, "aidev_logins", lambda data_dir: [])
    with pytest.raises(SystemExit, match="gave no AIDev login"):
        ep.main(*argv)
    assert not (prompts / "natural").exists()
    monkeypatch.setattr(scan, "aidev_logins", lambda data_dir: [LOGIN])
    ep.main(*argv)
    nat = prompts / "natural"
    assert (nat / "workflows" / f"{WORKFLOW}__{RUN}.js").read_text(encoding="utf-8").endswith(RULE)
    rows = {r["agent_id"]: r for r in map(json.loads, (nat / ep.NATURAL_PROMPTS).read_text(encoding="utf-8").splitlines())}
    assert rows["ahandle"]["withheld"].endswith("(handle)") and rows["aclean"]["prompt"] == CLEAN


def test_cli_refuses_screening_texts_that_miss_sampled_comments(session, prompts, tmp_path, screening):
    """The guard's screening texts must hold every comment of both repository manifests (684 sampled comments)."""
    texts, _ = screening
    nt = build_natural_task(tmp_path / "repo", index=False)
    redactions = tmp_path / "private.json"
    redactions.write_text(json.dumps({"patterns": [], "forbidden": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="lack"):
        ep.main(str(session), "--private-redactions", str(redactions), "--natural", "--natural-texts", str(nt.tasks_root),
                "--screening-texts", str(texts), "--aidev-logins", str(tmp_path), "--workflow", RUN)
    assert not (prompts / "natural").exists()
