"""JSON Lines readers split at line feeds only (``store.jsonl_lines``).

A JSON string may hold U+2028, U+2029 or U+0085 unescaped, and ``str.splitlines`` also splits at them, so it cut such a
record in two: an agent transcript holding a raw U+2028 was refused as "not JSON" when its generation record was made.
The readers of transcripts, run results, journals and logs now split at line feeds only. Synthetic data only; not
research evidence.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from tracecontract.ingest.sanitize_natural import sanitize_file
from tracecontract.store import jsonl_lines, read_jsonl

R = Path(__file__).resolve().parents[1]
SEPARATORS = [" ", " ", "\u0085"]


def _script(name: str):
    spec = importlib.util.spec_from_file_location(f"jsonl_test_{name}", R / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _jsonl(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def test_the_lines_are_splitlines_for_texts_without_the_three_characters():
    for text in ("", "a", "a\n", "a\nb", "a\nb\n", "a\r\nb\r\n", "\n", "\n\n", "x\n\ny\n", '{"k": "v"}\n{"k": 2}'):
        assert jsonl_lines(text) == text.splitlines(), repr(text)


@pytest.mark.parametrize("sep", SEPARATORS)
def test_a_record_that_holds_a_unicode_line_boundary_stays_whole(sep):
    records = [{"text": f"one{sep}two"}, {"n": 2}]
    text = _jsonl(records)
    assert len(text.splitlines()) == 3  # what the readers did before: the first record cut in two
    assert [json.loads(x) for x in jsonl_lines(text)] == records


class _Row(BaseModel):
    text: str


def _transcript(sep: str) -> list[dict]:
    return [
        {"type": "user", "timestamp": "2026-11-21T10:00:00Z", "message": {"role": "user", "content": f"start{sep}here"}},
        {"type": "assistant", "timestamp": "2026-11-21T10:00:05Z", "message": {"role": "assistant", "content": [
            {"type": "text", "text": f"plan{sep}next"},
            {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "/w/a.py", "content": f"x = 1{sep}"}},
        ]}},
    ]


@pytest.mark.parametrize("sep", SEPARATORS)
def test_the_readers_keep_such_records_whole(tmp_path, sep):
    rows = _transcript(sep)
    path = tmp_path / "agent-x.jsonl"
    path.write_text(_jsonl(rows), encoding="utf-8")

    assert _script("agent_run_record").read_entries(path) == rows
    calls = list(_script("strict_reaudit")._tool_calls(path))
    assert [(n, name, ti["content"]) for n, _, name, ti in calls] == [(2, "Write", f"x = 1{sep}")]

    store = tmp_path / "rows.jsonl"
    store.write_text(_jsonl([{"text": f"a{sep}b"}, {"text": "c"}]), encoding="utf-8")
    assert [r.text for r in read_jsonl(store, _Row)] == [f"a{sep}b", "c"]

    out = tmp_path / "out" / "agent-x.jsonl"
    sanitize_file(path, out)
    lines = out.read_text(encoding="utf-8").split("\n")
    assert lines[-1] == "" and len(lines) == len(rows) + 1  # one sanitised record per line, none cut
    assert [json.loads(x)["type"] for x in lines[:-1]] == ["user", "assistant"]


def test_the_phase_end_log_is_read_by_line_feeds(tmp_path):
    rpe = _script("record_phase_end")
    log = tmp_path / "phase_ends.jsonl"
    log.write_text(_jsonl([{"task_id": "NP-90", "phase": "P1", "note": "a b"},
                           {"task_id": "NP-90", "phase": "P2"}]), encoding="utf-8")
    assert rpe.last_phase(log, "NP-90") == "P2"
