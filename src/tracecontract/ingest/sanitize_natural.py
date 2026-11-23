"""Sanitiser for natural (third-party) session text, applied before any agent sees it (decision log D47).

``sanitize-natural:v1`` replaces, in every string of a session (event text, tool inputs,
metadata) or of a raw JSON or JSONL file:

* **secrets and tokens:** private-key blocks, JWTs, provider tokens (GitHub, GitLab, Slack, AWS,
  Google, OpenAI and Anthropic style ``sk-`` keys, Stripe, SendGrid, Twilio, npm, PyPI, Hugging
  Face), Azure storage keys, bearer and basic credentials, credentials in connection strings,
  Slack and Discord webhook URLs, and the values of ``KEY=value`` secrets (``*_TOKEN``,
  ``*_SECRET``, ``*PASSWORD*``, ``*API_KEY*`` ...);
* **e-mail addresses**, with the rule of ``sanitize:v2`` (``+@pytest.mark`` is not an address);
* **IP addresses:** IPv4 (loopback, unspecified and broadcast kept) and IPv6 (``::1`` kept);
* **@handles** in prose; decorators at the start of a line, CSS at-rules, JSDoc tags, npm scopes
  (``@types/node``), Svelte blocks (``{@html``) and the like are kept;
* **usernames:** in home-directory paths (``/home/<u>``, ``/Users/<u>``, ``C:\\Users\\<u>``,
  ``~<u>/``), in shell prompts (``<u>@<host>:``) and in the owner and group columns of
  ``ls -l`` listings; generic names (``user``, ``USER``, ``root`` ...) are kept.

Placeholders name what was removed and counts per kind are returned; nothing removed is kept.
This is best-effort: a personal name in prose, a novel token format or an internal host name
can still pass, so sanitised text stays personal data for retention purposes.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..schemas import EventKind, Session, sha256_bytes
from ..store import jsonl_lines
from .claude_code import _redact_emails

SANITIZER_VERSION = "sanitize-natural:v1"
SECRET = "[SECRET REDACTED]"

_Rule = tuple[str, re.Pattern[str], Callable[[re.Match[str]], str]]


def _const(text: str) -> Callable[[re.Match[str]], str]:
    return lambda _m: text


_SECRETS: list[_Rule] = [
    ("private_keys", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S),
     _const("[PRIVATE KEY REDACTED]")),
    ("secrets", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), _const(SECRET)),
    ("secrets", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}"
                           r"|xox[abprs]-[A-Za-z0-9-]{10,}|(?:AKIA|ASIA)[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}"
                           r"|ya29\.[0-9A-Za-z_-]{20,}|sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}|(?:sk|rk|pk)_(?:live|test)_"
                           r"[A-Za-z0-9]{16,}|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}|(?:SK|AC)[0-9a-fA-F]{32}"
                           r"|npm_[A-Za-z0-9]{36}|pypi-AgE[A-Za-z0-9_-]{50,}|hf_[A-Za-z0-9]{30,})\b"), _const(SECRET)),
    ("secrets", re.compile(r"https://(?:hooks\.slack\.com/services|(?:discord|discordapp)\.com/api/webhooks)/[\w/-]+"),
     _const("[WEBHOOK REDACTED]")),
    ("secrets", re.compile(r"(AccountKey=)[A-Za-z0-9+/=]{40,}"), lambda m: m.group(1) + SECRET),
    ("secrets", re.compile(r"(?i)\b(bearer|basic)(\s+)[A-Za-z0-9._~+/=-]{16,}"), lambda m: m.group(1) + m.group(2) + SECRET),
    ("secrets", re.compile(r"\b([a-z][a-z0-9+.-]{1,20}://)[^\s:/@'\"]+:[^\s@/'\"]+@"),
     lambda m: m.group(1) + "[CREDENTIALS REDACTED]@"),
    ("secrets", re.compile(r"(?i)\b([A-Z0-9_.-]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY"
                           r"|CLIENT[_-]?SECRET)[A-Z0-9_.-]*[\"']?)(\s*=\s*|\s*:(?!:)\s*)([\"']?)([^\s\"',;(){}\[\]<>$\\]{8,})\3"),
     lambda m: m.group(0) if _not_a_secret(m.group(4)) else m.group(1) + m.group(2) + m.group(3) + SECRET + m.group(3)),
]


def _not_a_secret(value: str) -> bool:
    """Values that are code or placeholders rather than secrets (``os.environ``, ``getToken``, ``true``):
    a secret value has a digit, or at least 24 characters, and is not a (dotted) identifier."""
    v = value.lower()
    return (v in ("true", "false", "null", "none", "undefined") or v.startswith(("process.env", "os.environ", "env.",
                                                                                 "self.", "this.", "[", "<", ":"))
            or bool(re.fullmatch(r"[A-Za-z_]+(?:\.[A-Za-z_]\w*)*|[\d.]+", value))
            or (not re.search(r"\d", value) and len(value) < 24))


_IPV4 = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.])")
_IPV6 = re.compile(r"(?<![\w:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
                   r"|(?:[0-9A-Fa-f]{1,4}:){1,6}:(?:[0-9A-Fa-f]{1,4}:){0,5}[0-9A-Fa-f]{1,4})(?![\w:])")
_KEEP_IP = re.compile(r"^(?:127\.|0\.0\.0\.0$|255\.255\.255\.)")

_CODE_AT = {
    "media", "import", "keyframes", "font-face", "supports", "layer", "tailwind", "apply", "use", "forward", "mixin",
    "include", "extend", "if", "else", "each", "return", "function", "charset", "namespace", "page", "container",
    "property", "param", "returns", "type", "typedef", "throws", "example", "see", "since", "deprecated",
    "override", "inheritdoc", "todo", "private", "public", "protected", "static", "const", "default", "description",
    "file", "license", "module", "prop", "readonly", "template", "this", "version", "ts-ignore", "ts-expect-error",
    "ts-nocheck", "jsx", "flow", "format", "vitest-environment", "jest-environment", "author", "callback", "enum",
    "event", "fires", "global", "memberof", "name", "async", "abstract", "class", "constructor", "interface",
    "implements", "augments", "link", "fileoverview", "summary", "variation", "vite-ignore", "click", "app", "pytest",
    "dataclass", "staticmethod", "classmethod", "cached", "lru_cache", "wraps", "Override", "Test", "Deprecated",
    "SuppressWarnings", "FunctionalInterface", "Autowired", "Component", "Bean", "Entity", "Inject", "Input", "Output",
    "Injectable", "NgModule", "tool", "router", "bot", "everyone", "here", "channel"}
_HANDLE = re.compile(r"(?<![\w.@/\\:+={`$-])@([A-Za-z0-9](?:[A-Za-z0-9_-]{0,38}))(?![\w(@/:=-]|\.\w)")
_LINE_START = re.compile(r"\s*(?:\d+(?:\t|\u2192))?\s*")  # optionally after a Read result's line number
_ANNOTATION = re.compile(r"[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+|Nullable|Nonnull|Override|Test|Deprecated")
_HOME = re.compile(r"(?i)((?:/home|/Users|/mnt/[a-z]/Users|\b[A-Za-z]:[\\/]+(?:Documents and Settings|Users))[\\/]+)"
                   r"([^\s/\\'\"`:;,<>|*?()\[\]{}]+)")
_TILDE = re.compile(r"(?<![\w~])~([a-z_][a-z0-9_.-]{0,31})(?=/)")
_PROMPT = re.compile(r"\b([a-z_][a-z0-9_.-]{0,31})@([A-Za-z0-9][A-Za-z0-9-]{1,62})(?=:(?:[~/]|\s*[A-Za-z]:))")
_LS_LONG = re.compile(r"(?m)^([dlcbps-][rwxsStT-]{9}[.+@]?\s+\d+\s+)(\S+)(\s+)(\S+)(?=\s+\d)")
_GENERIC_USERS = {"user", "users", "[user]", "<user>", "username", "$user", "${user}", "%username%", "root", "runner",
                  "ubuntu", "admin", "public", "default", "all users", "shared", "you", "me", "home", "nobody", "your-name",
                  "yourname", "<username>", "{user}", "{username}", "[redacted]", "name", "[name]", "[handle]"}


def _user(name: str, counter: Counter) -> str:
    if name.lower() in _GENERIC_USERS or name.isdigit() or name.startswith(("[", "$", "%", "<", "{")):
        return name
    counter["usernames"] += 1
    return "[USER]"


def sanitize_text(text: str, counter: Counter | None = None) -> str:
    """One string with secrets, e-mail addresses, IPs, @handles and usernames replaced."""
    c = counter if counter is not None else Counter()
    if not text:
        return text
    for kind, pat, repl in _SECRETS:
        def sub(m: re.Match[str], kind: str = kind, repl: Callable[[re.Match[str]], str] = repl) -> str:
            out = repl(m)
            if out != m.group(0):
                c[kind] += 1
            return out
        text = pat.sub(sub, text)
    emails: dict = {}
    text = _redact_emails(text, emails)
    if emails.get("emails"):
        c["emails"] += emails["emails"]

    def ip(m: re.Match[str]) -> str:
        if _KEEP_IP.match(m.group(0)) or m.group(0) == "::1":
            return m.group(0)
        if ":" in m.group(0) and (m.group(0).count(":") < 3 or not re.search(r"\d", m.group(0))):
            return m.group(0)  # a::b in code, not an address
        c["ips"] += 1
        return "[IP REDACTED]"

    text = _IPV6.sub(ip, _IPV4.sub(ip, text))
    text = _LS_LONG.sub(lambda m: m.group(1) + _user(m.group(2), c) + m.group(3) + _user(m.group(4), c), text)
    text = _HOME.sub(lambda m: m.group(1) + _user(m.group(2), c), text)
    text = _TILDE.sub(lambda m: "~" + _user(m.group(1), c), text)

    def prompt(m: re.Match[str]) -> str:
        c["hosts"] += 1
        return _user(m.group(1), c) + "@[HOST]"

    text = _PROMPT.sub(prompt, text)

    def handle(m: re.Match[str]) -> str:
        line_start = text.rfind("\n", 0, m.start()) + 1
        if m.group(1) in _CODE_AT or m.group(1).lower() in _CODE_AT or _ANNOTATION.fullmatch(m.group(1)) \
                or _LINE_START.fullmatch(text[line_start:m.start()]):
            return m.group(0)  # a decorator, annotation, at-rule or tag
        c["handles"] += 1
        return "@[HANDLE REDACTED]"

    return _HANDLE.sub(handle, text)


def sanitize_obj(obj: Any, counter: Counter | None = None) -> Any:
    """Every string in a JSON-like value sanitised (keys are kept)."""
    c = counter if counter is not None else Counter()
    if isinstance(obj, str):
        return sanitize_text(obj, c)
    if isinstance(obj, list):
        return [sanitize_obj(x, c) for x in obj]
    if isinstance(obj, dict):
        return {k: sanitize_obj(v, c) for k, v in obj.items()}
    return obj


def sanitize_session(session: Session) -> tuple[Session, dict[str, int]]:
    """A copy of ``session`` with sanitised event text, tool inputs and metadata, and the counts.

    Event ids and indices are unchanged; evidence quotes taken from the copy match the copy.
    """
    c: Counter = Counter()
    events = []
    for e in session.events:
        if e.kind == EventKind.tool_call and e.tool_input is not None:
            # The parser renders a tool call's text from its input (JSON, newlines escaped): sanitise
            # the input, whose strings have real line breaks, and render the text again.
            ti = sanitize_obj(e.tool_input, c)
            raw = ti.get("_raw") if set(ti) == {"_raw"} else ti
            events.append(e.model_copy(update={"tool_input": ti, "text": json.dumps(raw, sort_keys=True, ensure_ascii=False)
                                               if raw is not None else ""}))
        else:
            events.append(e.model_copy(update={"text": sanitize_text(e.text, c)}))
    meta = sanitize_obj(session.metadata, c)
    out = session.model_copy(update={"events": events, "metadata": meta,
                                     "repo_url": sanitize_text(session.repo_url, c) if session.repo_url else None})
    return out, dict(sorted(c.items()))


def sanitize_file(src: str | Path, dst: str | Path) -> dict[str, Any]:
    """Write a sanitised copy of a raw session file (``.jsonl`` line by line, else one JSON document).

    Lines that are not JSON are sanitised as text. Returns the sanitiser version, both sha256
    hashes and the counts per kind.
    """
    src, dst = Path(src), Path(dst)
    raw = src.read_bytes()
    c: Counter = Counter()
    text = raw.decode("utf-8", errors="replace")
    if src.suffix == ".jsonl":
        lines = []
        for line in jsonl_lines(text):
            try:
                lines.append(json.dumps(sanitize_obj(json.loads(line), c), ensure_ascii=False) if line.strip() else line)
            except json.JSONDecodeError:
                lines.append(sanitize_text(line, c))
        out = "\n".join(lines) + "\n"
    else:
        try:
            out = json.dumps(sanitize_obj(json.loads(text), c), ensure_ascii=False, indent=1) + "\n"
        except json.JSONDecodeError:
            out = sanitize_text(text, c)
    data = out.encode("utf-8")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return {"sanitizer": SANITIZER_VERSION, "source_sha256": sha256_bytes(raw), "sanitized_sha256": sha256_bytes(data),
            "redactions": dict(sorted(c.items()))}
