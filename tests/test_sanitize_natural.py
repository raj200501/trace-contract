"""The natural-data sanitiser (sanitize-natural:v1, decision log D47) on synthetic strings.

Token-shaped strings are assembled at runtime so that no credential-like literal sits in the
repository (the publication scan would flag it).
"""

from __future__ import annotations

import json
from collections import Counter

from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.ingest.sanitize_natural import SANITIZER_VERSION, sanitize_file, sanitize_session, sanitize_text
from tracecontract.schemas import Population

TOKEN = "gh" + "p_" + "Ab3dE6gH9k" * 4
ADDRESS = "jane.doe" + "@" + "example.com"
PEM = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIE\n-----END RSA " + "PRIVATE KEY-----"


def clean(text: str) -> tuple[str, dict]:
    c: Counter = Counter()
    return sanitize_text(text, c), dict(c)


def test_secrets_and_tokens():
    out, c = clean(f"GITHUB_TOKEN={TOKEN}\nDATABASE_URL=postgres://admin:pa55word@db:5432/x\nAuthorization: Bearer "
                   + "z" * 24 + f"\nPASSWORD=hunter2hunter2\n{PEM}")
    assert TOKEN not in out and "pa55word" not in out and "hunter2" not in out and "MIIE" not in out
    assert c == {"secrets": 4, "private_keys": 1}
    kept, c2 = clean("tokenizer = AutoTokenizer.from_pretrained('gpt2'); password = get_password(); token: string; "
                     "TokenKind::EndOfFile; self.tokens = tokens\\n; api_token = make_token")
    assert c2 == {} and "AutoTokenizer.from_pretrained" in kept and "TokenKind::EndOfFile" in kept


def test_emails_ips_and_handles():
    out, c = clean(f"mail {ADDRESS}, server 192.168.1.20:8080, loopback 127.0.0.1, v1.2.3.4, fe80::1ff:fe23:4567:890a, "
                   "std::vector, thanks @alice. see @types/node and @app.c")
    assert ADDRESS not in out and "192.168" not in out and "fe80" not in out and "alice" not in out
    assert "127.0.0.1" in out and "v1.2.3.4" in out and "std::vector" in out and "@types/node" in out and "@app.c" in out
    assert c == {"emails": 1, "ips": 2, "handles": 1}
    code, c2 = clean("@pytest.fixture\ndef f():\n    pass\n  @property\n@media screen {}\n{@html x}\ny = a @ b\n+@pytest.mark.x\n"
                     "<div @mousedown=\"go\"></div> public @NonNull String s; all:\n\t@echo done\n    12\t@echo off\n"
                     "context_tokens: 10000000")
    assert c2 == {} and code.startswith("@pytest.fixture")


def test_usernames():
    out, c = clean("C:\\Users\\alice\\proj; /home/bob/x; /Users/USER/ok; ~carol/y; /home/user/z\n"
                   "dave@DESKTOP-AB12CD:/mnt/d/proj> make\ndrwxr-xr-x 6 erin staff 192 Jun 1 12:00 src")
    for name in ("alice", "bob", "carol", "dave", "erin", "staff", "DESKTOP-AB12CD"):
        assert name not in out
    assert "/Users/USER/ok" in out and "/home/user/z" in out
    assert c == {"usernames": 6, "hosts": 1}


def test_session_and_file(tmp_path):
    rows = [{"type": "user", "sessionId": "S", "cwd": "/home/frank/p", "message": {"role": "user",
             "content": f"Email {ADDRESS} about /home/frank/p"}},
            {"type": "assistant", "sessionId": "S", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": f"export API_KEY={TOKEN}"}},
                {"type": "tool_use", "id": "t2", "name": "Write", "input": {"file_path": "/p/Makefile",
                                                                             "content": "all:\n\t@echo built\n"}}]}}]
    src = tmp_path / "s.jsonl"
    src.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    s = parse_claude_code_jsonl(src, population=Population.natural, source="fixture")
    copy, counts = sanitize_session(s)
    blob = json.dumps(copy.model_dump(mode="json"))
    assert "frank" not in blob and ADDRESS not in blob and TOKEN not in blob
    assert [e.event_id for e in copy.events] == [e.event_id for e in s.events]
    assert counts["secrets"] == 1 and TOKEN not in copy.events[1].text  # the call's text is rendered from its input
    assert "handles" not in counts and "@echo built" in copy.events[2].tool_input["content"]
    rec = sanitize_file(src, tmp_path / "out" / "s.jsonl")
    text = (tmp_path / "out" / "s.jsonl").read_text()
    assert rec["sanitizer"] == SANITIZER_VERSION and "frank" not in text and TOKEN not in text
    assert rec["redactions"] == {"emails": 1, "secrets": 1, "usernames": 2}
