"""scripts/agent_run_record.py: the generation record of an agent run, from its transcript; combined records.

The transcripts are synthetic, in the layout of a session's records: <records>/<session id>/subagents/workflows/
<workflow run id>/agent-<id>.jsonl, with the workflow's journal beside them. The session id, the workflow and agent ids
and the names in the model fields are made up; the test checks that none of those names reaches a record.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tracecontract.schemas import GenerationRecord, VerifierCondition
from tracecontract.verifier import (
    GENERATION_RUN_KEYS,
    build_spec,
    generation_record_problems,
)

R = Path(__file__).resolve().parents[1]
SID = "5f0c3a1e-2b4d-4c6e-8a0b-1c2d3e4f5a6b"  # a made-up session id
WF = "wf_0a1b2c3d-4e5"
AGENT = "a0f1e2d3c4b5a6978"
MODEL = "acme-zephyr-9"  # a made-up model name, written where the harness writes the model
FRAME = ("[Workflow harness — computed task] The task text below was computed at runtime by a workflow script. "
         "The computed task text follows:")
TASK = ("You are the B3 test writer for task NP-99.\n\nWrite tests under /ws/NP-99/diff-derived/tests "
        "only.\n    an indented line stays indented\nReply with the list of tests.")
T0, T_END = "2026-11-22T10:00:00.250Z", "2026-11-22T10:07:31Z"


def _load():
    spec = importlib.util.spec_from_file_location("agent_run_record", R / "scripts" / "agent_run_record.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


arr = _load()


def framed(task: str, *, indent_empty: bool = False) -> str:
    return FRAME + "\n" + "\n".join("  " + ln if ln or indent_empty else ln for ln in task.split("\n"))


def _user(text, ts, **kw):
    return {"type": "user", "timestamp": ts, "sessionId": SID, "message": {"role": "user", "content": text}, **kw}


def _assistant(mid, blocks, ts):
    return {"type": "assistant", "timestamp": ts, "sessionId": SID, "requestedModel": MODEL,
            "message": {"id": mid, "role": "assistant", "model": MODEL, "content": blocks}}


def _tool(tid, name="Bash"):
    return {"type": "tool_use", "id": tid, "name": name, "input": {"command": "true"}}


def _result(tid, ts):
    return _user([{"type": "tool_result", "tool_use_id": tid, "content": "ok"}], ts)


def _at(start: str, seconds: float) -> str:
    t = datetime.fromisoformat(start) + timedelta(seconds=seconds)
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def rows(prompt: str | None = None, *, start: str = T0, end: str = T_END) -> list[dict]:
    """A run: the prompt, harness entries, one message split over three entries (thinking and two tool calls), two
    more messages within ten seconds of the start, and a last harness entry at ``end``. Three turns, three tool calls."""
    return [
        _user(framed(TASK) if prompt is None else prompt, start),
        {"type": "attachment", "timestamp": _at(start, 0.01), "attachment": {"type": "date"}},
        _user("<system-reminder>harness context</system-reminder>", _at(start, 0.02), isMeta=True),
        _assistant("msg_01", [{"type": "thinking", "thinking": "plan"}], _at(start, 5)),
        _assistant("msg_01", [_tool("t1")], _at(start, 6)),
        _assistant("msg_01", [_tool("t2", "Read")], _at(start, 6.5)),
        _result("t1", _at(start, 7)),
        _result("t2", _at(start, 7.1)),
        _assistant("msg_02", [_tool("t3", "Write")], _at(start, 8)),
        _result("t3", _at(start, 9)),
        _assistant("msg_03", [{"type": "text", "text": "D1 to D4 written"}], _at(start, 9.5)),
        {"type": "attachment", "timestamp": end, "attachment": {"type": "total_tokens_reminder"}},
    ]


def write_run(root: Path, entries: list[dict], *, agent: str = AGENT, wf: str | None = WF, finished: bool | None = True,
              meta_model: str | None = "zephyr") -> Path:
    """The transcript under <root>/records/<session id>/subagents/[workflows/<wf>/]agent-<id>.jsonl, its .meta.json and,
    for a workflow agent, the workflow's journal (finished None: no journal entry for the agent)."""
    d = root / "records" / SID / "subagents" / ("workflows/" + wf if wf else "")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"agent-{agent}.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    if meta_model:
        (d / f"agent-{agent}.meta.json").write_text(json.dumps({"agentType": "workflow-subagent", "model": meta_model}))
    if wf and finished is not None:
        with (d / "journal.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "started", "agentId": agent, "label": "testgen:diff_derived:NP-99"}) + "\n")
            if finished:
                fh.write(json.dumps({"type": "result", "agentId": agent, "result": {}}) + "\n")
    return path


def record(capsys, *argv) -> tuple[int, dict | None, str]:
    code = arr.main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, (json.loads(out.out) if out.out.strip() else None), out.err


def refused(capsys, *argv) -> str:
    code, rec, err = record(capsys, *argv)
    assert code == 2 and rec is None and "refused, nothing printed" in err, (code, rec, err)
    return err


# --------------------------------------------------------------------------- one run


def test_a_workflow_transcript_gives_a_complete_record_without_model_or_session(tmp_path, capsys):
    path = write_run(tmp_path, rows())
    code, raw, _ = record(capsys, path, "--config", "config-A", "--label", "diff-derived")
    assert code == 0
    rec = GenerationRecord.model_validate(raw)
    assert generation_record_problems(rec) == []
    assert rec.generator == "config-A" and rec.run_id == f"{WF}/diff-derived"
    # the hash is of the workflow script's text, without the harness frame and indent: the template instantiation
    assert rec.prompt_sha256 == hashlib.sha256(TASK.encode()).hexdigest()
    assert rec.budget == {"started_at": T0, "ended_at": T_END, "wall_s": 450.75, "turns": 3, "tool_calls": 3,
                          "run_record": f"build-session:subagents/workflows/{WF}/agent-{AGENT}.jsonl"}
    assert set(rec.budget) <= set(GENERATION_RUN_KEYS) and rec.created_at == T_END
    assert hashlib.sha256(path.read_bytes()).hexdigest() in rec.notes and "computed task" in rec.notes
    text = json.dumps(raw).lower()
    for absent in (SID, str(tmp_path).lower(), "acme", "zephyr", "records/", "/ws/"):
        assert absent not in text, absent
    # It is what build-verifier needs to record a generated verifier.
    tests = tmp_path / "task" / "verifiers" / "diff_derived" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_d.py").write_text(textwrap.dedent("""
        from tc_sandbox import run_python

        def test_d1():
            r = run_python("result = 1")
            assert r.ok and r.value == 1
    """))
    spec = build_spec(verifier_id="diff_derived", task_id="NP-99", condition=VerifierCondition.diff_derived,
                      test_dir=tests, task_dir=tmp_path / "task", generation=rec, require_generation=True)
    assert spec.generation == rec


def test_the_prompt_is_the_computed_task_or_else_the_first_user_message(tmp_path, capsys):
    want = hashlib.sha256(TASK.encode()).hexdigest()
    # empty lines indented or not by the harness: the same text
    p = write_run(tmp_path / "a", rows(framed(TASK, indent_empty=True)))
    assert record(capsys, p, "--config", "config-A", "--label", "x")[1]["prompt_sha256"] == want
    # a relayed user request first, then the computed task: the computed task
    two = rows()
    two.insert(0, _user("[Workflow harness — user request] The harness relays the request:\n  please build it", T0))
    p = write_run(tmp_path / "b", two)
    assert record(capsys, p, "--config", "config-A", "--label", "x")[1]["prompt_sha256"] == want
    # an agent outside a workflow: the first user message verbatim; its run id needs --workflow
    plain = "Write the reference checks for NP-99.\n  (indented, kept as it is)"
    p = write_run(tmp_path / "c", rows(plain), wf=None)
    err = refused(capsys, p, "--config", "config-A", "--label", "refcheck")
    assert "give --workflow" in err
    code, raw, _ = record(capsys, p, "--config", "config-A", "--label", "refcheck", "--workflow", "standalone")
    assert code == 0 and raw["run_id"] == "standalone/refcheck"
    assert raw["prompt_sha256"] == hashlib.sha256(plain.encode()).hexdigest() and "verbatim" in raw["notes"]
    assert raw["budget"]["run_record"] == f"build-session:subagents/agent-{AGENT}.jsonl"
    # a framed message after the first assistant message is not the first prompt
    late = rows(plain)
    late.insert(4, _user(framed("another task"), _at(T0, 5.5)))
    p = write_run(tmp_path / "d", late)
    assert record(capsys, p, "--config", "config-A", "--label", "x")[1]["prompt_sha256"] == hashlib.sha256(
        plain.encode()).hexdigest()


def test_turns_count_messages_and_tool_calls_count_blocks_once(tmp_path, capsys):
    entries = rows()
    entries.insert(6, _assistant("msg_01", [_tool("t2", "Read")], _at(T0, 6.6)))  # a repeated block
    entries.insert(9, _assistant("msg_04", [{"type": "server_tool_use", "id": "s1", "name": "lookup", "input": {}}],
                                 _at(T0, 7.6)))
    entries.insert(9, {"type": "assistant", "timestamp": _at(T0, 7.5),  # no message id: its own turn
                       "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Bash", "input": {}}]}})
    p = write_run(tmp_path, entries)
    raw = record(capsys, p, "--config", "config-B", "--label", "x")[1]
    assert (raw["budget"]["turns"], raw["budget"]["tool_calls"]) == (5, 5)


def test_records_that_would_be_incomplete_or_name_the_model_are_refused(tmp_path, capsys):
    p = write_run(tmp_path / "ok", rows())
    for config in ("A", "config-a", "config-AB", "model:x", "config-", MODEL):
        refused(capsys, p, "--config", config, "--label", "x")
    for label in ("two words", "a/b", "a+b", "a;b", "@x", "-x"):
        refused(capsys, p, "--config", "config-A", f"--label={label}")
    # a label or workflow holding the model the transcript records, or a part of one
    assert "model name" in refused(capsys, p, "--config", "config-A", "--label", "zephyr-labeler")
    standalone = write_run(tmp_path / "standalone", rows(), wf=None)
    assert "model name" in refused(capsys, standalone, "--config", "config-A", "--label", "x", "--workflow", "ACME-run")
    refused(capsys, p, "--config", "config-A")  # no label
    # --workflow may only repeat the transcript's own workflow directory
    assert "not the transcript's workflow" in refused(capsys, p, "--config", "config-A", "--label", "x",
                                                      "--workflow", "wf_ffffffff-fff")
    assert record(capsys, p, "--config", "config-A", "--label", "x", "--workflow", WF)[1]["run_id"] == f"{WF}/x"
    # a transcript that is still being written, or that gives no positive wall time, a zone-less time or no prompt
    bad = write_run(tmp_path / "cut", rows())
    bad.write_text(bad.read_text() + '{"type": "assistant", "timest', encoding="utf-8")
    assert "not JSON" in refused(capsys, bad, "--config", "config-A", "--label", "x")
    one = write_run(tmp_path / "one", [_user(framed(TASK), T0), _assistant("m", [], T0)])
    assert "wall time" in refused(capsys, one, "--config", "config-A", "--label", "x")
    naive = write_run(tmp_path / "naive", rows(end="2026-11-22T10:07:31"))
    assert "time zone" in refused(capsys, naive, "--config", "config-A", "--label", "x")
    noprompt = write_run(tmp_path / "noprompt", [_assistant("m", [], T0), _user("late", T_END)])
    assert "no user prompt" in refused(capsys, noprompt, "--config", "config-A", "--label", "x")
    unindented = write_run(tmp_path / "frame", rows(FRAME + "\n  first line\nnot indented"))
    assert "not indented" in refused(capsys, unindented, "--config", "config-A", "--label", "x")


def test_the_pointer_is_relative_to_the_session_directory(tmp_path, capsys):
    d = tmp_path / "elsewhere" / WF
    d.mkdir(parents=True)
    p = d / f"agent-{AGENT}.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in rows()), encoding="utf-8")
    if not any(arr.SESSION_DIR.fullmatch(a.name) for a in p.resolve().parents):  # e.g. a temporary dir in a session
        assert "session directory" in refused(capsys, p, "--config", "config-A", "--label", "x")
    code, raw, _ = record(capsys, p, "--config", "config-A", "--label", "x", "--session-dir", tmp_path / "elsewhere")
    assert code == 0 and raw["budget"]["run_record"] == f"build-session:{WF}/agent-{AGENT}.jsonl"
    assert "inside the session directory" in refused(capsys, p, "--config", "config-A", "--label", "x",
                                                     "--session-dir", tmp_path / "other")


def test_a_long_interval_between_entries_is_noted_and_warned(tmp_path, capsys):
    """Two 20-second stretches five hours apart (an agent resumed later): wall_s still counts the whole span, as the
    record's times say, but the notes give the interval and a warning is printed."""
    entries = rows(end=_at(T0, 20))
    entries += [_user("Please also add a test for the empty case.", _at(T0, 18000)),
                _assistant("msg_09", [_tool("t9")], _at(T0, 18005)), _result("t9", _at(T0, 18010)),
                _assistant("msg_10", [{"type": "text", "text": "added"}], _at(T0, 18020))]
    code, raw, err = record(capsys, write_run(tmp_path / "resumed", entries), "--config", "config-A", "--label", "x")
    assert code == 0 and raw["budget"]["wall_s"] == 18020.0 and raw["budget"]["turns"] == 5
    assert "the longest interval between two consecutive entries is 17980.0 s" in raw["notes"]
    assert f"(from {_at(T0, 20)} to {_at(T0, 18000)}), which wall_s counts" in raw["notes"]
    assert "warning" in err and "interval of 17980.0 s" in err
    # an ordinary run: the interval is noted, without a warning
    code, raw, err = record(capsys, write_run(tmp_path / "plain", rows()), "--config", "config-A", "--label", "x")
    assert code == 0 and "the longest interval between two consecutive entries is 441.25 s" in raw["notes"]
    assert err == "" and "which wall_s counts" not in raw["notes"]


def test_an_agent_without_a_result_in_the_journal_needs_unfinished(tmp_path, capsys):
    p = write_run(tmp_path, rows(), finished=False)
    assert "--unfinished" in refused(capsys, p, "--config", "config-A", "--label", "x")
    code, raw, _ = record(capsys, p, "--config", "config-A", "--label", "x", "--unfinished")
    assert code == 0 and "journal records no result" in raw["notes"]
    assert not generation_record_problems(GenerationRecord.model_validate(raw))
    # no journal entry for the agent at all: nothing to say
    q = write_run(tmp_path / "nojournal", rows(), finished=None)
    code, raw, _ = record(capsys, q, "--config", "config-A", "--label", "x")
    assert code == 0 and "journal" not in raw["notes"]


# --------------------------------------------------------------------------- combined records


def _run_file(tmp_path: Path, capsys, name: str, label: str, start: str, end: str, *, config: str = "config-A",
              prompt: str = TASK, finished: bool = True) -> tuple[Path, dict]:
    p = write_run(tmp_path / name, rows(framed(prompt), start=start, end=end), agent="a" + hashlib.sha256(
        name.encode()).hexdigest()[:16], finished=finished)
    code, raw, _ = record(capsys, p, "--config", config, "--label", label, *(() if finished else ("--unfinished",)))
    assert code == 0 and raw is not None
    out = tmp_path / f"{name}.json"
    out.write_text(json.dumps(raw), encoding="utf-8")
    return out, raw


def test_combine_sums_a_generator_and_its_revisers(tmp_path, capsys):
    g, gen = _run_file(tmp_path, capsys, "gen", "testgen-initial", T0, "2026-11-22T10:20:00Z")
    r1, rev1 = _run_file(tmp_path, capsys, "rev1", "revise-initial-1", "2026-11-22T11:00:00Z", "2026-11-22T11:10:00.5Z",
                         prompt="Revise the tests.")
    r2, rev2 = _run_file(tmp_path, capsys, "rev2", "revise-initial-2", "2026-11-22T12:00:00Z", "2026-11-22T12:05:00Z",
                         prompt="Revise the tests again.")
    code, raw, _ = record(capsys, "--combine", r2, g, r1)  # given in any order: combined in start order
    assert code == 0
    rec = GenerationRecord.model_validate(raw)
    assert generation_record_problems(rec) == []
    runs = [gen, rev1, rev2]
    assert rec.run_id == "+".join(x["run_id"] for x in runs) and rec.generator == "config-A"
    assert rec.prompt_sha256 == gen["prompt_sha256"] != rev1["prompt_sha256"]
    assert rec.budget["started_at"] == T0 and rec.budget["ended_at"] == "2026-11-22T12:05:00Z" == rec.created_at
    for k in ("turns", "tool_calls"):
        assert rec.budget[k] == sum(x["budget"][k] for x in runs)
    assert rec.budget["wall_s"] == round(sum(x["budget"]["wall_s"] for x in runs), 3)
    assert rec.budget["run_record"] == ";".join(x["budget"]["run_record"] for x in runs)
    assert "tokens" not in rec.budget
    for x in runs:
        assert x["run_id"] in rec.notes and x["prompt_sha256"] in rec.notes
    # a combined record combines further, e.g. with a later reviser
    both = tmp_path / "both.json"
    both.write_text(json.dumps(record(capsys, "--combine", g, r1)[1]), encoding="utf-8")
    code, again, _ = record(capsys, "--combine", both, r2)
    assert code == 0 and again["run_id"] == rec.run_id and again["budget"]["wall_s"] == rec.budget["wall_s"]


def test_combined_notes_keep_what_each_run_discloses(tmp_path, capsys):
    """A generator recorded with --unfinished, then a finished reviser: the combined record says so, and keeps each
    run's own notes (its transcript's sha256 and the form of prompt hashed), also when combined again."""
    g, gen = _run_file(tmp_path, capsys, "gen", "testgen-full", T0, "2026-11-22T10:20:00Z", finished=False)
    r1, rev1 = _run_file(tmp_path, capsys, "rev1", "revise-full-1", "2026-11-22T11:00:00Z", "2026-11-22T11:10:00Z")
    r2, rev2 = _run_file(tmp_path, capsys, "rev2", "revise-full-2", "2026-11-22T12:00:00Z", "2026-11-22T12:10:00Z")
    assert "journal records no result" in gen["notes"]
    code, raw, _ = record(capsys, "--combine", r1, g)
    assert code == 0 and not generation_record_problems(GenerationRecord.model_validate(raw))
    assert f"Recorded with --unfinished (no result in the workflow's journal): [1] {gen['run_id']}." in raw["notes"]
    for run in (gen, rev1):
        assert run["notes"] in raw["notes"]  # the transcript's sha256, the prompt form, the --unfinished disclosure
    both = tmp_path / "both.json"
    both.write_text(json.dumps(raw), encoding="utf-8")
    code, again, _ = record(capsys, "--combine", both, r2)
    assert code == 0 and "Recorded with --unfinished" in again["notes"]
    assert all(run["notes"] in again["notes"] for run in (gen, rev1, rev2))
    # without an unfinished run, nothing is said about one
    assert "--unfinished" not in record(capsys, "--combine", r1, r2)[1]["notes"]


def test_combine_refuses_what_is_not_one_chain_of_complete_records(tmp_path, capsys):
    g, _ = _run_file(tmp_path, capsys, "gen", "testgen-full", T0, "2026-11-22T10:20:00Z")
    over, _ = _run_file(tmp_path, capsys, "over", "revise-full-1", "2026-11-22T10:10:00Z", "2026-11-22T10:30:00Z")
    other, _ = _run_file(tmp_path, capsys, "cfgb", "labeler", "2026-11-22T11:00:00Z", "2026-11-22T11:10:00Z",
                         config="config-B")
    later, _ = _run_file(tmp_path, capsys, "later", "revise-full-1", "2026-11-22T11:00:00Z", "2026-11-22T11:10:00Z")
    assert "one after another" in refused(capsys, "--combine", g, over)
    assert "different configurations" in refused(capsys, "--combine", g, other)
    assert "given twice" in refused(capsys, "--combine", g, later, g)
    # two different agents of one workflow recorded with the same label share a run id: refused as such
    same, _ = _run_file(tmp_path, capsys, "rerun", "testgen-full", "2026-11-22T12:00:00Z", "2026-11-22T12:20:00Z")
    assert "share the run id" in refused(capsys, "--combine", g, same)
    assert "two or more" in refused(capsys, "--combine", g)
    pilot = tmp_path / "pilot.json"  # a pilot-style record: run id unrecorded, no hash, no budget
    pilot.write_text(json.dumps({"generator": "model:x", "run_id": "unrecorded", "prompt_sha256": "",
                                 "created_at": "2026-11-13T00:00:00Z"}))
    assert "incomplete generation record" in refused(capsys, "--combine", g, pilot)
    transcript = write_run(tmp_path / "t", rows())
    assert "not transcripts" in refused(capsys, "--combine", g, transcript)
    assert "only records" in refused(capsys, "--combine", g, later, "--config", "config-A")
