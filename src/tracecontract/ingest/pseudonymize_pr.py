"""Pseudonymiser for natural PR-review texts in the stages after S9 (protocol v0.7 §15.6, v0.8 §16.4; D47, D48, D51).

The texts of the S9 sample were made by ``scripts/screen_aidev.py``, whose stages S1 to S8a are
frozen as implemented. A verification found three gaps in its pseudonymiser (D51): the repository
URL keeps its owner's login, a link ``github.com/<login>/<repo>`` keeps a login when the person is
not one of the PR's participants, and git author names that contain a space are never treated as
known names. :class:`PRPseudonymizer` is the pseudonymiser of the later stages (S10 and building
natural tasks). In one left-to-right pass, so that a label is never replaced again, it:

* removes e-mail addresses and links to user profiles (``github.com/<login>``, the users API,
  avatars), as before;
* masks the account in every GitHub link (``github.com``, ``gist.github.com``,
  ``raw.githubusercontent.com``, ``api.github.com/repos``, ``<x>.github.io``): the repository owner
  under the ``{owner}`` rule, a known login by its label, and any other account that is a person
  login in AIDev (``persons``) by a ``user-N`` label; known logins later in the link's path are
  replaced too;
* replaces known logins and @handles by role labels (reviewer, pr-author, issue-author,
  repo-owner, agent), other participants and unknown @handles by ``user-N``, bot accounts by
  ``bot-N`` and handles that address a coding agent by ``agent``;
* treats git author names that contain a space as known names (``user-N``), matched as a whole
  phrase with any whitespace between the words;
* keeps code tokens intact: an ``@name`` that is a decorator or docstring tag (:data:`CODE_AT`),
  or is followed by ``(``, ``.name``, ``_`` or ``@`` (a login has no underscore), or that stands in
  decorator position (only whitespace and a diff marker before it on its line) inside code: a text
  passed with ``code=True`` (a diff hunk) or a fenced code block. Inside code, any other ``@name`` is
  masked only if it is a known login or a person login in AIDev. ``+@pytest.mark`` and
  ``x@pytest.mark.slow`` are not e-mail addresses;
* masks model identifiers (:data:`MODEL_PLACEHOLDER`).

The ``{owner}`` rule is the one of ``data/manifests/screening_natural_aidev.json``: the owner's
name is replaced by ``{owner}`` when the owner acts as an account in AIDev (authored a PR, review
comment, issue or commit), and kept when it never does (an organisation). :func:`mask_repo_url`
applies it to a repository URL, also inside the repository's name.

The module is pure: the caller reads AIDev (with DuckDB, under ``python -I``) and passes the logins
in. It writes nothing, and the texts it makes stay outside the repository (D47).
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterable, Mapping

# Handles that address a coding agent (lower case, without a ``[bot]`` suffix): pseudonymised as "agent".
# The same set as AGENT_HANDLES in scripts/screen_aidev.py.
AGENT_HANDLES = frozenset({"copilot", "copilot-swe-agent", "claude", "codex", "chatgpt-codex-connector", "cursor",
                           "cursoragent", "devin-ai-integration", "google-labs-jules", "jules"})
# Python decorators and docstring tags: an @word that is one of these is code, not a handle. The set of
# scripts/screen_aidev.py, with two more decorators of the standard library. (Names with an underscore,
# such as ``@freeze_time``, are code by their form: a login has no underscore.)
CODE_AT = frozenset({"property", "staticmethod", "classmethod", "abstractmethod", "dataclass", "override", "overload",
                     "cached_property", "contextmanager", "asynccontextmanager", "final", "total_ordering",
                     "singledispatch", "unique", "fixture", "computed_field", "login_required", "csrf_exempt",
                     "shared_task", "task", "tool", "njit", "jit", "lru_cache", "cache", "param", "return", "returns",
                     "rtype", "type", "raise", "raises", "see", "since", "note", "todo", "deprecated", "example",
                     "singledispatchmethod", "abstractproperty"})
OWNER = "{owner}"
MODEL_PLACEHOLDER = "[model identifier removed]"
EMAIL_PLACEHOLDER = "[email removed]"
PROFILE_PLACEHOLDER = "[profile link removed]"

LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}(?:\[bot\])?"
_EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
_URL_CHARS = r"[^\s)\]>\"'<`]"
# A GitHub link, with or without its scheme, or an SSH remote; ``<x>.github.io`` names an account in its host.
_SSH = "git@github.com:"
_LINK = (rf"(?:https?://|(?<![\w.@/-]))(?:(?:www\.|gist\.)?github\.com|raw\.githubusercontent\.com|api\.github\.com"
         rf"|avatars\.githubusercontent\.com)/{_URL_CHARS}*|(?<![\w.@/-]){re.escape(_SSH)}{_URL_CHARS}*"
         rf"|(?:https?://|(?<![\w.@/-]))[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){{0,38}}\.github\.io\b{_URL_CHARS}*")
# Model identifiers: a model family's name followed by a version, a size or a tier (case-insensitive).
_VER = r"\d+(?:\.\d+)*[a-z]?"
_TIER = r"(?:opus|sonnet|haiku|instant)"
MODEL = re.compile(
    rf"\b(?:chat)?gpt-?{_VER}(?:-[a-z0-9.]+)*|\bgpt-(?:oss|j|neox?)\b[a-z0-9.-]*"
    rf"|\bo[1-9](?:-(?:mini|pro|preview|high|low|medium))+\b"
    rf"|\bclaude-(?:[a-z]+-)*(?:v?[1-9]|{_TIER})[a-z0-9.-]*"  # versions start at 1: not the session directory claude-0
    rf"|\bclaude[ _]+(?:{_VER}[ _]+)?{_TIER}(?:[ _]+{_VER})?\b|\bclaude[ _]+{_VER}\b"
    rf"|\bgemini-{_VER}[a-z0-9.-]*|\bgemini[ _]+{_VER}(?:[ _]+(?:pro|flash|ultra|nano))?\b"
    rf"|\b(?:code)?llama-?{_VER}[\w.-]*|\bllama[ _]+{_VER}\b"
    rf"|\b(?:mistral|mixtral|codestral|ministral|devstral|magistral)-[a-z0-9.-]*\d[a-z0-9.-]*"
    rf"|\bdeepseek-(?:coder|chat|reasoner|r\d|v\d)[a-z0-9.-]*"
    rf"|\bqwen{_VER}?-[a-z0-9.-]+|\bqwen\d[a-z0-9.]*\b"
    rf"|\b(?:text|code)-davinci-\d+|\bdavinci-\d+|\bphi-{_VER}[a-z0-9.-]*|\bgrok-{_VER}[a-z0-9.-]*|\bcommand-r\b[a-z0-9+.-]*",
    re.I)
_FENCE = re.compile(r"^[ \t]*(?:[+\- ][ \t]*)?(```|~~~)", re.M)
_DECORATOR_LINE = re.compile(r"(?:^|\n)[ \t]*(?:[+\- ][ \t]*)?$")


def is_code_at(text: str, at: int, end: int) -> bool:
    """Whether ``text[at:end]``, an ``@name``, is code rather than a handle by its own form: a decorator or docstring
    tag (:data:`CODE_AT`), or followed by ``(``, ``.name``, ``_`` or ``@`` (a template such as ``@NAME@``)."""
    if text[at + 1:end].lower() in CODE_AT:
        return True
    nxt = text[end:end + 2]
    return nxt[:1] in ("(", "_", "@") or (nxt[:1] == "." and nxt[1:2].isidentifier())


def in_decorator_position(text: str, at: int) -> bool:
    """Only whitespace and an optional diff marker stand before ``text[at]`` on its line."""
    return bool(_DECORATOR_LINE.search(text, max(0, text.rfind("\n", 0, at)), at))


def code_spans(text: str) -> list[tuple[int, int]]:
    """Fenced code blocks (``` or ~~~, to the closing fence or the end of the text), as (start, end)."""
    spans, pos = [], 0
    while (m := _FENCE.search(text, pos)) is not None:
        close = re.compile(rf"^[ \t]*(?:[+\- ][ \t]*)?{re.escape(m.group(1))}", re.M).search(text, m.end())
        end = close.end() if close else len(text)
        spans.append((m.start(), end))
        pos = end
    return spans


def owner_pattern(owner: str) -> re.Pattern[str]:
    """The owner's name inside a repository name or a path: not part of a longer alphanumeric word."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(owner)}(?![A-Za-z0-9])", re.I)


def mask_repo_url(url: str, owner_acts_as_account: bool) -> str:
    """``https://github.com/<owner>/<name>`` with the owner, also inside the name, replaced by ``{owner}`` when the
    owner acts as an account in AIDev; unchanged for an organisation (the ``{owner}`` rule)."""
    m = re.match(r"(https?://(?:www\.)?github\.com/|https://api\.github\.com/repos/)([^/\s]+)(/[^\s]*)?$", url)
    if not m or not owner_acts_as_account:
        return url
    owner = m.group(2)
    return m.group(1) + OWNER + owner_pattern(owner).sub(OWNER, m.group(3) or "")


class PRPseudonymizer:
    """Pseudonymise the texts of one PR thread (see the module docstring).

    ``roles``: known logins and their labels (reviewer, pr-author, issue-author, agent ...). ``others``:
    further participants' logins, labelled ``user-1``, ``user-2`` ... on first appearance, as are unknown
    @handles. ``names``: git author names that contain a space, labelled the same way. ``bots``: bot
    accounts (``bot-N``). ``persons``: the person logins of AIDev, whose accounts are masked in links.
    ``owner``: the repository owner; with ``owner_acts_as_account`` it is a known login labelled
    ``repo-owner`` and becomes ``{owner}`` in links.
    """

    def __init__(self, roles: Mapping[str, str], others: Iterable[str] = (), *, names: Iterable[str] = (),
                 bots: Iterable[str] = (), persons: Iterable[str] = (), owner: str | None = None,
                 owner_acts_as_account: bool = False) -> None:
        self.roles = {k.lower(): v for k, v in roles.items() if k}
        self.owner = owner.lower() if owner and owner_acts_as_account else None
        if self.owner:
            self.roles.setdefault(self.owner, "repo-owner")
        self.others = {o.lower() for o in others if o} - set(self.roles)
        self.names = {" ".join(n.split()).lower() for n in names if n and " " in n.strip()} - set(self.roles)
        self.bots = frozenset(b.lower() for b in bots)
        # A frozenset is used as given (lower-case logins), so that the AIDev set is not copied for every PR.
        self.persons = persons if isinstance(persons, frozenset) else frozenset(p.lower() for p in persons)
        self.counts: dict[str, int] = {}
        logins = sorted(set(self.roles) | self.others, key=len, reverse=True)
        phrases = sorted(self.names, key=len, reverse=True)
        known = [re.escape(x) for x in logins] + [r"\s+".join(map(re.escape, n.split())) for n in phrases]
        self._known = re.compile(r"(?<![A-Za-z0-9_@-])(?:" + "|".join(known) + r")(?![A-Za-z0-9_-])", re.I) if known else None
        alts = [rf"(?P<link>{_LINK})", rf"(?P<email>{_EMAIL})", rf"(?<![A-Za-z0-9._%+/-])@(?P<handle>{LOGIN})",
                rf"(?P<model>{MODEL.pattern})"]
        if self._known is not None:
            alts.append(rf"(?P<known>{self._known.pattern})")
        self._re = re.compile("|".join(alts), re.I)

    def label(self, login: str) -> str:
        h = " ".join(login.split()).lower()
        if h not in self.roles:
            base = h.removesuffix("[bot]")
            if base in AGENT_HANDLES:
                self.roles[h] = "agent"
            else:
                kind = "bot" if h in self.bots or base + "[bot]" in self.bots or h.endswith("[bot]") else "user"
                self.roles[h] = f"{kind}-{sum(v.startswith(kind + '-') for v in self.roles.values()) + 1}"
        return self.roles[h]

    def _count(self, what: str) -> None:
        self.counts[what] = self.counts.get(what, 0) + 1

    def _known_sub(self, text: str) -> str:
        if self._known is None:
            return text

        def sub(m: re.Match[str]) -> str:
            self._count("login")
            return self.label(m.group(0))

        return self._known.sub(sub, text)

    def _account(self, name: str) -> str:
        low = name.lower()
        if self.owner and low == self.owner:
            self._count("owner")
            return OWNER
        if low in self.roles or low in self.others or low in self.persons:
            self._count("link_account")
            return self.label(name)
        return name

    def _path(self, prefix: str, segs: list[str], i: int) -> str:
        """``prefix`` and the path ``segs`` with the account ``segs[i]`` masked, and the owner and known logins after it."""
        account, rest = segs[i], "/".join(segs[i + 1:])
        if self.owner and account.lower() == self.owner:
            rest = owner_pattern(self.owner).sub(OWNER, rest)  # the owner's name inside the repository's name
        head = "/".join([*segs[:i], self._account(account)])
        return prefix + head + ("/" + self._known_sub(rest) if i + 1 < len(segs) else "")

    def _link(self, s: str) -> str:
        core = s.rstrip(".,;:!?")  # trailing punctuation ends a sentence, not the link
        tail = s[len(core):]
        if core.lower().startswith(_SSH):
            segs = core[len(_SSH):].split("/")
            return (self._path(core[:len(_SSH)], segs, 0) if segs[0] else core) + tail
        scheme = core[:core.index("//") + 2] if core.lower().startswith(("http://", "https://")) else ""
        host, slash, path = core[len(scheme):].partition("/")
        h = host.lower()
        segs = path.split("/") if path else []
        real = [x.split("?", 1)[0].split("#", 1)[0] for x in segs if x]
        if h.endswith(".github.io"):
            account = host[:-len(".github.io")]
            return scheme + self._account(account) + host[len(account):] + slash + self._known_sub(path) + tail
        if h == "avatars.githubusercontent.com" or (h == "api.github.com" and real[:1] == ["users"]) or (
                h in ("github.com", "www.github.com") and (len(real) == 1 or (len(real) == 2 and real[0].lower() == "sponsors"))):
            self._count("profile_link")
            return PROFILE_PLACEHOLDER + tail
        i = (1 if real[:1] == ["repos"] else None) if h == "api.github.com" else 0
        if i is None or len(segs) <= i or not segs[i]:
            return s
        return self._path(scheme + host + slash, segs, i) + tail

    def _handle(self, m: re.Match[str], code: bool, spans: list[tuple[int, int]], starts: list[int]) -> str:
        name = m.group("handle")
        low = name.lower()
        known = low in self.roles or low in self.others
        k = bisect.bisect_right(starts, m.start()) - 1
        in_code = code or (k >= 0 and spans[k][0] <= m.start() < spans[k][1])
        if in_code and in_decorator_position(m.string, m.start()):
            return m.group(0)  # a decorator line inside code, whatever it names
        if not known and is_code_at(m.string, m.start(), m.end()):
            return m.group(0)
        if in_code and not known and low not in self.persons and low not in self.bots:
            return m.group(0)  # an @name in code that is not a login we know of
        self._count("handle")
        return "@" + self.label(name)

    def __call__(self, text: str | None, *, code: bool = False) -> str | None:
        """The pseudonymised text; ``code=True`` for a text that is code (a diff hunk)."""
        if text is None:
            return None
        spans = code_spans(text)
        starts = [a for a, _ in spans]

        def sub(m: re.Match[str]) -> str:
            if m.group("email"):
                local, _, domain = m.group(0).partition("@")
                if not re.search(r"[A-Za-z0-9]", local) or domain.lower().startswith("pytest."):
                    return m.group(0)  # a diff marker or a name before a decorator, not an address
                self._count("email")
                return EMAIL_PLACEHOLDER
            if m.group("link"):
                return self._link(m.group(0))
            if m.group("handle"):
                return self._handle(m, code, spans, starts)
            if m.group("model"):
                self._count("model_identifier")
                return MODEL_PLACEHOLDER
            self._count("name" if " " in m.group(0).strip() else "login")
            return self.label(m.group(0))

        return self._re.sub(sub, text)

    def repo_url(self, url: str) -> str:
        """The repository URL under the ``{owner}`` rule (:func:`mask_repo_url`): the owner acts as an account if it is
        this thread's owner given with ``owner_acts_as_account``, or a person login in AIDev."""
        m = re.match(r"https?://(?:www\.)?github\.com/([^/\s]+)|https://api\.github\.com/repos/([^/\s]+)", url)
        owner = (m.group(1) or m.group(2)).lower() if m else None
        return mask_repo_url(url, owner is not None and (owner == self.owner or owner in self.persons))
