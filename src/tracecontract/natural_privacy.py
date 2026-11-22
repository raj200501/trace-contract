"""Matchers for the natural arm's private material in texts that git could publish (protocol §17.4; decision log D47,
D48, D52).

A natural PR-review task holds third-party material: the pseudonymised PR thread in ``session.json``, the quotes of its
contracts, and the repository's code (its candidates' patches, its verifiers' tests, its base snapshot). That material
stays under the git-ignored ``data/natural/``, and the texts of every comment that the screening stage sampled stay
outside the repository. These matchers find it in other texts, for ``scripts/scan_tracked_files.py --natural-texts``, the
natural guard of ``scripts/export_prompts.py`` and ``scripts/publish_natural_run.py``. A match is given by where it lies
and the task (or screened comment) it comes from, never by the text matched.

* :class:`TextWindows`: verbatim thread text. A window is 60 consecutive characters, or 8 consecutive words, of a
  session event's text, of a contract quote or of a screened comment's texts. A text too short for a window of words is
  matched whole, down to a minimum below which it is too generic to tell apart (``MIN_WHOLE_WORDS`` words with a letter
  and ``MIN_WHOLE_CHARS`` characters, or ``MIN_WHOLE_DENSE`` characters of a script written without spaces).
* :class:`RepositoryNames`: a natural task's repository, by its name and by its owner in the URL form ``/<owner>``.
* :class:`CodeLines`: lines of a natural task's code (its candidates' patches, its verifiers' files, and the lines of
  its base snapshot's Python files that name something of their own, :func:`distinctive_line`), or the check ids of
  its verifiers.

:class:`NaturalMaterial` loads all of them for every task directory under a tasks root (``data/natural/tasks``), with
the tasks' base snapshots, and for the screening texts given; :func:`task_code` gives the code lines and check ids of
one task. A task file that exists but cannot be read, and a base snapshot that a task records but that is missing or
holds no code line, are errors (:class:`MaterialError`), never skipped: the checks fail closed. A file with a NUL byte
(an image among a verifier's files) holds no line of code; such files are counted (:attr:`NaturalMaterial.binary`) so
that the checks can say what they did not read.
"""

from __future__ import annotations

import bisect
import html
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from itertools import accumulate, compress
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

WINDOW_CHARS = 60
WINDOW_WORDS = 8
MIN_WINDOW_WORDS = 4  # words with a letter that a usable window holds
MIN_WINDOW_DENSE = 20  # ... or characters of a script written without spaces (Han, kana, Thai ...) in a character window
# A text with no window of words is matched whole if it holds MIN_WHOLE_WORDS words with a letter, in two
# whitespace-separated tokens, and MIN_WHOLE_CHARS characters (whitespace collapsed), or MIN_WHOLE_DENSE characters of a
# script written without spaces. Below that ("Looks good", "Use a set.") a text is too generic to tell apart.
MIN_WHOLE_WORDS = 3
MIN_WHOLE_CHARS = 12
MIN_WHOLE_DENSE = 8
CHAR_STRIDE = 20  # the searched text is looked up at every CHAR_STRIDE-th character ...
WORD_STRIDE = 4  # ... and at every WORD_STRIDE-th word
MAX_ESCAPE_LEVELS = 3  # backslash escapes decoded this many times over: a JSON string inside a JSON string ...
MIN_CODE_LINE = 24  # characters of a code line, after its whitespace is collapsed ...
MIN_CODE_WORD = 4  # ... and the characters of its longest word: a line of short words only is too generic
CODE_SUFFIXES = (".py", ".pyi", ".pyx", ".pxd")  # the base snapshot's files whose lines count as code (all of them read)
BASE_RARE_LINES = 1  # a base snapshot's line counts if a word of it is in at most this many lines of the generic corpus
MASKED_OWNER = "{owner}"  # ingest.pseudonymize_pr.OWNER: the owner masked by the {owner} rule (a person)

_WS = re.compile(r"\s+")
_WS_RUN = re.compile(r"\s{2,}")
_WORD = re.compile(r"\w+")
_WORD_SPLIT = re.compile(r"(\w+)")  # a text split into the runs between words and the words
# Scripts written without spaces between words: Thai, Lao, Myanmar, Khmer, kana and Han.
_DENSE_RANGES = "฀-໿က-႟ក-៿぀-ヿ㐀-䶿一-鿿豈-﫿\U00020000-\U0002fa1f"
_DENSE = re.compile(f"[{_DENSE_RANGES}]")
# The tokens of a whole-text match: one character of such a script, or a run of other word characters.
_WHOLE_TOKEN = re.compile(f"[{_DENSE_RANGES}]|[^\\W{_DENSE_RANGES}]+")
# Backslash escapes of JSON, Python and Markdown: a surrogate pair, \uXXXX, \xXX, or one escaped character.
_ESCAPE = re.compile(r"\\(?:u([dD][89abAB][0-9a-fA-F]{2})\\u([dD][c-fC-F][0-9a-fA-F]{2})|u([0-9a-fA-F]{4})"
                     r"|x([0-9a-fA-F]{2})|(.))", re.DOTALL)
_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v"}
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s[^<>]*)?/?>")  # an HTML or XML tag
_LINE_NUMBER = re.compile(r"^[ \t]*\d+(?:\t|→)", re.MULTILINE)  # cat -n, and the arrow form of a file viewer
_PERCENT = re.compile(r"(?:%[0-9A-Fa-f]{2})+")
_DOMAIN = r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
# A frame of a Python traceback, and the standard library's location. An installed package (site-packages,
# dist-packages) is not the standard library: it may be the natural repository's own package.
_FRAME = re.compile(r'^([ \t]*)File "([^"\n]*)", line \d+(?:, in [^\r\n]*)?[ \t]*\r?$', re.MULTILINE)
_STDLIB_PATH = re.compile(r"[/\\]lib[/\\]python\d[\d.]*[/\\]|\\Lib\\|^<frozen |^<string>$")
_INSTALLED_PATH = re.compile(r"[/\\](?:site|dist)-packages[/\\]")
_MARKERS = re.compile(r"[ \t]*[\^~]+[ \t]*")
# Tool output that names no one: a section banner of pytest (``==== short test summary info ====``, ``____ test_x ____``,
# ``---- Captured stdout call ----``), pip's resolver errors, which name a package, and the header lines of a Python
# traceback and of a chained exception.
_TOOL_LINE = re.compile(r"^[ \t]*(?:([=_*#~-])\1{2,}[ \t]+\S[^\r\n]*?[ \t]+\1{3,}"
                        r"|(?:ERROR: )?(?:Could not find a version that satisfies the requirement|"
                        r"No matching distribution found for)\b[^\r\n]*"
                        r"|Traceback \(most recent call last\):"
                        r"|During handling of the above exception, another exception occurred:"
                        r"|The above exception was the direct cause of the following exception:)[ \t]*\r?$", re.MULTILINE)
MIN_GENERIC_WORDS = 2  # words of a line that the generic lines (:func:`generic_lines`) hold and that a cut needs
_DIFF_HEADERS =("diff --git ", "index ", "--- ", "+++ ", "@@", "new file mode", "deleted file mode", "old mode",
                 "new mode", "similarity index", "dissimilarity index", "rename from", "rename to", "copy from",
                 "copy to", "Binary files", "\\ No newline")


def _mark_class() -> str:
    """The characters that compose with the character before them (``unicodedata.combining``, and the Hangul vowel and
    final jamo), as the body of a regex character class."""
    marks = [c for c in range(0x0300, 0x10000) if unicodedata.combining(chr(c)) or 0x1160 <= c <= 0x11FF]
    ranges: list[list[int]] = []
    for c in marks:
        if ranges and c == ranges[-1][1] + 1:
            ranges[-1][1] = c
        else:
            ranges.append([c, c])
    return "".join(chr(a) if a == b else f"{chr(a)}-{chr(b)}" for a, b in ranges)


_MARKS = _mark_class()
_COMPOSABLE = re.compile(f"[^{_MARKS}][{_MARKS}]+")  # a character and the marks that follow it (a decomposed letter)
# LaTeX markup that splits or adds words in a quote (the paper is LaTeX): \verb|...|, the accents (na\"ive, \'{e},
# \c{c}), the special letters (\ss, \o), the escaped specials (\_, \&), the spaces (~, \,), the groups' braces and every
# other command's name, which is dropped (\texttt{os.replace} reads os.replace). Read only in a text that holds such
# markup (_LATEX_TRIGGER): a command with an argument, \verb, or an accent inside a word or on a braced letter.
_LATEX_TRIGGER = re.compile(r"\\(?:[A-Za-z]{2,}\*?\s*[{\[]|verb\*?[^\sA-Za-z*])|(?<=[A-Za-z{])\\[\"'`^~=][A-Za-z{]"
                            r"|\\[\"'`^~=.HcbdkruvG]\{[A-Za-z]\}")
_LATEX = re.compile(
    r"\\verb\*?([^\sA-Za-z*])([^\n]*?)\1"  # 1, 2: \verb|...| (on one line), read as its content
    r"|\\([\"'`^~=.])\s*(?:\{\s*([A-Za-z]|\\[ij])\s*\}|([A-Za-z]|\\[ij](?![A-Za-z])[ \t]?))"  # 3-5: an accent on a letter
    r"|\\([HcbdkruvG])(?:\s*\{\s*([A-Za-z]|\\[ij])\s*\}|\s+([A-Za-z]))"  # 6-8: an accent named by a letter
    r"|\\(ss|ae|AE|oe|OE|aa|AA|o|O|l|L|i|j)(?![A-Za-z])(?:\{\}|[ \t])?"  # 9: a special letter, and the space it ends
    r"|\\([A-Za-z]+)\*?"  # 10: any other command: dropped
    r"|\\([_&%#$\{\}])"  # 11: an escaped special character
    r"|\\[ ,;:]|~|\\\\|\}\s*\{"  # a space, a thin space, a tie, a line break, the gap between two arguments: a space
    r"|\\[-/!]|[{}]",  # a discretionary hyphen, an italic correction, a negative space, a group's brace: nothing
    re.DOTALL)
_LATEX_ACCENTS = {'"': "\u0308", "'": "\u0301", "`": "\u0300", "^": "\u0302", "~": "\u0303", "=": "\u0304", ".": "\u0307",
                  "H": "\u030b", "c": "\u0327", "b": "\u0331", "d": "\u0323", "k": "\u0328", "r": "\u030a", "u": "\u0306",
                  "v": "\u030c", "G": "\u030f"}
_LATEX_LETTERS = {"ss": "ß", "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ", "aa": "å", "AA": "Å", "o": "ø", "O": "Ø",
                  "l": "ł", "L": "Ł", "i": "i", "j": "j"}


def _lower(text: str) -> str:
    """The text lower-cased without moving any offset: U+0130 (the one character whose lower case is two characters)
    becomes ``i`` first."""
    return text.lower() if text.isascii() else text.replace("İ", "i").lower()


def normalise(text: str) -> str:
    """The form in which windows are compared: composed (NFC), every run of whitespace as one space, letters
    lower-cased."""
    return _lower(_WS.sub(" ", text if text.isascii() else unicodedata.normalize("NFC", text)))


_NOT_LETTERS = str.maketrans("", "", "0123456789_")


def _lettered(word: str) -> bool:
    """Whether a word (a run of word characters) holds a letter; an ASCII word character is a letter, a digit or ``_``."""
    return bool(word.translate(_NOT_LETTERS)) if word.isascii() else any(c.isalpha() for c in word)


def _wordchar(c: str) -> bool:
    return c.isalnum() or c == "_"


# ---------------------------------------------------------------------------------------------------------------------
# Views of a searched text, and offsets back into it
# ---------------------------------------------------------------------------------------------------------------------


class _View:
    """A text as a reader of the file sees it (as written, or with its escapes, character references, tags, line numbers
    or percent-encoding decoded), with a map from its offsets to those of the text it was decoded from (``parent``, else
    the searched text)."""

    def __init__(self, text: str, anchors: tuple[list[int], list[int]] | None = None, parent: _View | None = None) -> None:
        self.text = text
        self._anchors = anchors  # (view offset, parent offset) right after each decoded sequence
        self._parent = parent

    def to_source(self, k: int) -> int:
        if self._anchors is not None:
            vs, ts = self._anchors
            i = bisect.bisect_right(vs, k) - 1
            k = ts[i] + (k - vs[i])
        return k if self._parent is None else self._parent.to_source(k)


def _decoded(text: str, pattern: re.Pattern[str], decode: Callable[[re.Match[str]], str],
             parent: _View | None = None) -> _View | None:
    """``text`` with every match of ``pattern`` replaced by ``decode(match)``, as a view; None if nothing changes. Every
    decoder shortens what it replaces (or keeps its length), so an offset maps back inside the replaced sequence."""
    parts: list[str] = []
    vs, ts = [0], [0]
    last = n = 0
    for m in pattern.finditer(text):
        s, e = m.span()
        rep = decode(m)
        parts.append(text[last:s])
        parts.append(rep)
        n += (s - last) + len(rep)
        vs.append(n)
        ts.append(e)
        last = e
    if len(vs) == 1:
        return None
    parts.append(text[last:])
    out = "".join(parts)
    return None if out == text else _View(out, (vs, ts), parent)


def _unescape(m: re.Match[str]) -> str:
    hi, lo, u, x, c = m.groups()
    if hi:
        return chr(0x10000 + ((int(hi, 16) - 0xD800) << 10) + (int(lo, 16) - 0xDC00))
    if u or x:
        return chr(int(u or x, 16))
    return _SIMPLE_ESCAPES.get(c, c)


def _unentity(m: re.Match[str]) -> str:
    return html.unescape(m.group(0))


def _untag(m: re.Match[str]) -> str:
    return " "


def _unnumber(m: re.Match[str]) -> str:
    return ""


def _unpercent(m: re.Match[str]) -> str:
    return unquote(m.group(0), errors="replace")


def _compose(m: re.Match[str]) -> str:
    """A letter and its marks in NFC form, unless that is longer (a decoder never lengthens what it replaces)."""
    s = m.group(0)
    out = unicodedata.normalize("NFC", s)
    return out if len(out) <= len(s) else s


def _unlatex(m: re.Match[str]) -> str:
    """The text that a match of ``_LATEX`` stands for: no longer than the match."""
    g = m.groups()
    if g[0] is not None:  # \verb
        return g[1]
    if g[2] is not None or g[5] is not None:  # an accent
        base = next(x for x in (g[3], g[4], g[6], g[7]) if x is not None).rstrip()  # a letter, \i or \j
        return unicodedata.normalize("NFC", base[-1] + _LATEX_ACCENTS[g[2] or g[5]])
    if g[8] is not None:
        return _LATEX_LETTERS[g[8]]
    if g[9] is not None:
        return ""
    if g[10] is not None:
        return g[10]
    s = m.group(0)
    return " " if s in ("~", "\\\\") or s[:2] in ("\\ ", "\\,", "\\;", "\\:") or (s[0] == "}" and len(s) > 1) else ""


# The decoders of the fully decoded view, after the backslash escapes, in order: (trigger, pattern, decode).
_DECODERS: tuple[tuple[str, re.Pattern[str], Callable[[re.Match[str]], str]], ...] = (
    ("&", _ENTITY, _unentity), ("<", _TAG, _untag), ("", _LINE_NUMBER, _unnumber), ("%", _PERCENT, _unpercent))


def _composed(view: _View) -> _View | None:
    """``view`` with its decomposed letters composed (NFC: a copy of a text in NFD form), or None if nothing changes."""
    return None if view.text.isascii() else _decoded(view.text, _COMPOSABLE, _compose, view)


def _fully_decoded(view: _View) -> _View:
    """``view`` with its backslash escapes decoded up to ``MAX_ESCAPE_LEVELS`` times over (a JSON string inside a JSON
    string), then its HTML character references, its tags (as spaces), the line numbers that start its lines and its
    percent-encoding decoded, and its decomposed letters composed (NFC)."""
    v = view
    for _ in range(MAX_ESCAPE_LEVELS):
        w = _decoded(v.text, _ESCAPE, _unescape, v) if "\\" in v.text else None
        if w is None:
            break
        v = w
    for trigger, pattern, decode in _DECODERS:
        if trigger in v.text and (w := _decoded(v.text, pattern, decode, v)) is not None:
            v = w
    return _composed(v) or v


def _views(text: str) -> list[_View]:
    """The text as written, with its backslash escapes decoded (a JSON string, a Python literal, Markdown), with its HTML
    character references decoded (an HTML page), fully decoded (:func:`_fully_decoded`: a JSON string inside a JSON
    string, an HTML page's text without its tags, a file viewer's numbered lines, a percent-encoded URL, a text in NFD
    form) and, for a text with LaTeX markup (as written, or inside a JSON string), with that markup read (``_LATEX``:
    ``\\texttt{...}``, ``\\verb|...|``, ``na\\"ive``), as far as each changes it."""
    base = _View(text)
    out = [base]
    if "\\" in text and (v := _decoded(text, _ESCAPE, _unescape)) is not None:
        out.append(v)
    if "&" in text and (v := _decoded(text, _ENTITY, _unentity)) is not None:
        out.append(v)
    full = _fully_decoded(base)
    if all(full.text != v.text for v in out):
        out.append(full)
    for v in out[:2] if "\\" in text else ():  # LaTeX as written, and inside a JSON string (its escapes decoded)
        if _LATEX_TRIGGER.search(v.text) and (w := _decoded(v.text, _LATEX, _unlatex, v)) is not None:
            w = _composed(w) or w
            if all(w.text != x.text for x in out):
                out.append(w)
    return out


def text_views(text: str) -> list[_View]:
    """The views in which the matchers read ``text`` (see :class:`TextWindows`), to be computed once and passed to each
    matcher's ``find``."""
    return _views(text)


class _Normalised:
    """A view with its whitespace collapsed (and, with ``lower``, its letters lower-cased); maps its offsets back."""

    def __init__(self, view: _View, *, lower: bool = True) -> None:
        self.view = view
        collapsed = _WS.sub(" ", view.text)
        self.text = _lower(collapsed) if lower else collapsed
        self._ws: tuple[list[int], list[int]] | None = None
        self._tokens: list[str] | None = None
        self._token_starts: list[int] | None = None

    @property
    def tokens(self) -> list[str]:
        if self._tokens is None:
            self._tokens = _WORD.findall(self.text)
        return self._tokens

    def token_offset(self, t: int) -> int:
        if self._token_starts is None:
            self._token_starts = [m.start() for m in _WORD.finditer(self.text)]
        return self._token_starts[t]

    def to_source(self, k: int) -> int:
        """The offset in the searched text of offset ``k`` of this normalised view."""
        if self._ws is None:
            ns, vs = [0], [0]
            shift = 0
            for m in _WS_RUN.finditer(self.view.text):
                shift += m.end() - m.start() - 1
                ns.append(m.end() - shift)
                vs.append(m.end())
            self._ws = (ns, vs)
        ns, vs = self._ws
        i = bisect.bisect_right(ns, k) - 1
        return self.view.to_source(vs[i] + (k - ns[i]))


def _common_left(a: Sequence[Any], i: int, b: Sequence[Any], j: int) -> int:
    """How many items before ``a[i]`` and ``b[j]`` are equal, going left."""
    k, lim = 0, min(i, j)
    while k < lim:
        step = min(64, lim - k)
        if a[i - k - step:i - k] == b[j - k - step:j - k]:
            k += step
            continue
        while k < lim and a[i - k - 1] == b[j - k - 1]:
            k += 1
        return k
    return k


def _common_right(a: Sequence[Any], i: int, b: Sequence[Any], j: int) -> int:
    """How many items from ``a[i]`` and ``b[j]`` on are equal."""
    k, lim = 0, min(len(a) - i, len(b) - j)
    while k < lim:
        step = min(64, lim - k)
        if a[i + k:i + k + step] == b[j + k:j + k + step]:
            k += step
            continue
        while k < lim and a[i + k] == b[j + k]:
            k += 1
        return k
    return k


# ---------------------------------------------------------------------------------------------------------------------
# Thread text
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class _Source:
    label: str
    text: str  # normalised
    chars: list[int]  # starts of the usable character windows, ascending
    tokens: list[str]
    words: list[int]  # starts (token indexes) of the usable word windows, ascending


class TextWindows:
    """Windows of the natural texts, and where a searched text holds one.

    Both sides are compared in :func:`normalise` form: composed (NFC), whitespace runs as one space, letters lower-cased.
    A word is a run of letters, digits and underscores, so punctuation and markup between words do not count. The
    searched text is read as written, with its backslash escapes decoded, with its HTML character references decoded,
    fully decoded (a JSON string inside a JSON string, an HTML page without its tags, numbered lines, percent-encoding,
    decomposed letters) and with its LaTeX markup read (``\\texttt{...}``, ``\\verb|...|``, accent commands), so that a
    thread text is found in those forms too.

    A window is used only if it holds at least ``min_words`` words with a letter and spans at least two
    whitespace-separated tokens, or if it is a character window holding ``min_dense`` characters of a script written
    without spaces (Chinese, Japanese, Thai ...). A window inside one token (a path, a URL, an identifier, a rule of
    dashes) is not used: the manifests record such tokens by design (the commented file's path, D48), and a URL of a
    natural repository is :class:`RepositoryNames`'s concern.

    A text with no usable window of words (fewer than ``words`` words, such as a short review comment) is also matched
    whole, provided it holds ``MIN_WHOLE_WORDS`` words with a letter in two whitespace-separated tokens and
    ``MIN_WHOLE_CHARS`` characters, or ``MIN_WHOLE_DENSE`` characters of a script written without spaces: the searched
    text must hold all of its tokens in a row (a token is a run of word characters, or one character of such a script),
    so whitespace, case and the punctuation and markup between the words do not count, in every view of the searched
    text (JSON-escaped, HTML-escaped ...). A shorter text, such as a two-word comment, is not matched: it is too generic
    to tell apart, and the study's own texts hold such phrases.

    The window search is exact. The searched text is looked up at every ``char_stride``-th character (every
    ``word_stride``-th word) with a seed of ``chars - char_stride + 1`` characters (``words - word_stride + 1`` words),
    each seed is extended to the longest run the searched text and a natural text have in common, and a common run that
    holds a usable window is a match, one per natural text and common run. Every common run of a window's length holds
    such a seed.
    """

    def __init__(self, texts: Iterable[tuple[str, str]], *, chars: int = WINDOW_CHARS, words: int = WINDOW_WORDS,
                 min_words: int = MIN_WINDOW_WORDS, min_dense: int = MIN_WINDOW_DENSE, char_stride: int = CHAR_STRIDE,
                 word_stride: int = WORD_STRIDE) -> None:
        """``texts``: ``(label, text)``: its windows are used, and it is matched whole if it has no usable window of
        words and reaches the minimum."""
        if not (0 < char_stride <= chars and 0 < word_stride <= words):
            raise ValueError("a stride must lie between 1 and the window's length")
        self.chars, self.words, self.min_words, self.min_dense = chars, words, min_words, min_dense
        self._cstride, self._wstride = char_stride, word_stride
        self._cseed, self._wseed = chars - char_stride + 1, words - word_stride + 1
        self._sources: list[_Source] = []
        self._char_seeds: dict[str, list[tuple[int, int]]] = {}
        self._word_seeds: dict[tuple[str, ...], list[tuple[int, int]]] = {}
        self._whole: dict[str, list[tuple[tuple[str, ...], str]]] = {}  # first token -> (tokens, label)
        seen: set[tuple[str, str]] = set()
        for label, text in texts:
            norm = normalise(text)
            if (label, norm) not in seen:
                seen.add((label, norm))
                self._add(label, norm)

    @property
    def n_texts(self) -> int:
        """The texts that have a usable window."""
        return len(self._sources)

    @property
    def n_char_windows(self) -> int:
        return sum(len(s.chars) for s in self._sources)

    @property
    def n_word_windows(self) -> int:
        return sum(len(s.words) for s in self._sources)

    @property
    def n_whole(self) -> int:
        """The texts matched whole."""
        return sum(len(v) for v in self._whole.values())

    @staticmethod
    def whole_tokens(norm: str) -> tuple[str, ...] | None:
        """The tokens by which a text (:func:`normalise` form) with no usable window of words is matched whole, or None
        if it is below the minimum (``MIN_WHOLE_WORDS`` words with a letter in two whitespace-separated tokens and
        ``MIN_WHOLE_CHARS`` characters, or ``MIN_WHOLE_DENSE`` characters of a script written without spaces)."""
        stripped = norm.strip()
        dense = 0 if stripped.isascii() else len(_DENSE.findall(stripped))
        lettered = sum(1 for w in _WORD.findall(stripped) if _lettered(w))
        if dense < MIN_WHOLE_DENSE and not (lettered >= MIN_WHOLE_WORDS and len(stripped) >= MIN_WHOLE_CHARS
                                            and " " in stripped):
            return None
        return tuple(_WHOLE_TOKEN.findall(stripped)) or None

    def _add(self, label: str, norm: str) -> None:
        idx = len(self._sources)
        matches = list(_WORD.finditer(norm))
        tokens = [m.group() for m in matches]
        spaces = list(accumulate((c == " " for c in norm), initial=0))  # spaces[i]: spaces before offset i
        marks = bytearray(len(norm))
        for m in matches:
            if _lettered(m.group()):
                marks[m.start()] = 1
        letters = list(accumulate(marks, initial=0))  # word starts with a letter before offset i
        dense = None if norm.isascii() else list(accumulate(
            (c >= "฀" and _DENSE.match(c) is not None for c in norm), initial=0))
        cw, ww = self.chars, self.words
        # A space strictly inside the window: characters of two tokens.
        chars = [q for q in range(len(norm) - cw + 1)
                 if (spaces[q + cw - 1] > spaces[q + 1] and letters[q + cw] - letters[q] >= self.min_words)
                 or (dense is not None and dense[q + cw] - dense[q] >= self.min_dense)]
        ws_ids = [spaces[m.start()] for m in matches]  # the whitespace-separated token a word belongs to
        wl = list(accumulate((_lettered(t) for t in tokens), initial=0))
        words = [t for t in range(len(tokens) - ww + 1)
                 if ws_ids[t] != ws_ids[t + ww - 1] and wl[t + ww] - wl[t] >= self.min_words]
        if not words and (toks := self.whole_tokens(norm)) is not None:
            self._whole.setdefault(toks[0], []).append((toks, label))
        if not chars and not words:
            return
        self._sources.append(_Source(label, norm, chars, tokens, words))
        # A seed at r lies inside a usable window starting at q iff r - (length - seed) <= q <= r.
        cs, slack = self._cseed, cw - self._cseed
        for r in range(len(norm) - cs + 1):
            i = bisect.bisect_left(chars, r - slack)
            if i < len(chars) and chars[i] <= r:
                self._char_seeds.setdefault(norm[r:r + cs], []).append((idx, r))
        ws_, wslack = self._wseed, ww - self._wseed
        for r in range(len(tokens) - ws_ + 1):
            i = bisect.bisect_left(words, r - wslack)
            if i < len(words) and words[i] <= r:
                self._word_seeds.setdefault(tuple(tokens[r:r + ws_]), []).append((idx, r))

    def find(self, text: str, views: Sequence[_View] | None = None) -> list[tuple[int, str, str]]:
        """Each match in ``text``: (offset in ``text``, ``"characters"``, ``"words"`` or ``"whole"``, the label of the
        natural text), one per common run, sorted. The matched text is not returned. ``views``: ``text_views(text)``,
        if already computed."""
        found: dict[tuple[int, str, str], None] = {}
        if not self._sources and not self._whole:
            return []
        for view in views if views is not None else _views(text):
            nv = _Normalised(view)
            for k, src in self._find_chars(nv.text):
                found[(nv.to_source(k), "characters", self._sources[src].label)] = None
            for t, src in self._find_words(nv.tokens):
                found[(nv.to_source(nv.token_offset(t)), "words", self._sources[src].label)] = None
            for k, label in self._find_whole(nv.text):
                found[(nv.to_source(k), "whole", label)] = None
        return sorted(found)

    def _find_chars(self, f: str) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        cs, cw = self._cseed, self.chars
        done: dict[int, int] = {}  # natural text -> where in f the last common run found with it ends
        for p in range(0, len(f) - cs + 1, self._cstride):
            for src, r in self._char_seeds.get(f[p:p + cs], ()):
                if done.get(src, -1) > p:
                    continue  # inside a common run already found with this text
                s = self._sources[src]
                lo = r - _common_left(f, p, s.text, r)
                hi = r + cs + _common_right(f, p + cs, s.text, r + cs)
                i = bisect.bisect_left(s.chars, lo)
                if i < len(s.chars) and s.chars[i] + cw <= hi:
                    out.append((s.chars[i] - r + p, src))
                    done[src] = hi - r + p
        return out

    def _find_words(self, toks: list[str]) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        ws_, ww = self._wseed, self.words
        done: dict[int, int] = {}
        for p in range(0, len(toks) - ws_ + 1, self._wstride):
            for src, r in self._word_seeds.get(tuple(toks[p:p + ws_]), ()):
                if done.get(src, -1) > p:
                    continue
                s = self._sources[src]
                lo = r - _common_left(toks, p, s.tokens, r)
                hi = r + ws_ + _common_right(toks, p + ws_, s.tokens, r + ws_)
                i = bisect.bisect_left(s.words, lo)
                if i < len(s.words) and s.words[i] + ww <= hi:
                    out.append((s.words[i] - r + p, src))
                    done[src] = hi - r + p
        return out

    def _find_whole(self, f: str) -> list[tuple[int, str]]:
        """The whole texts that ``f`` holds: only those all of whose tokens ``f`` holds are looked for, at each
        occurrence of their first token."""
        hits: list[tuple[int, str]] = []
        if not self._whole:
            return hits
        toks = _WHOLE_TOKEN.findall(f)
        present = set(toks)
        for first, cands in self._whole.items():
            live = [(t, label) for t, label in cands if present.issuperset(t)] if first in present else []
            i = -1
            while live:
                try:
                    i = toks.index(first, i + 1)
                except ValueError:
                    break
                hits.extend((i, label) for t, label in live if tuple(toks[i:i + len(t)]) == t)
        if not hits:
            return hits
        starts = [m.start() for m in _WHOLE_TOKEN.finditer(f)]
        return [(starts[i], label) for i, label in hits]


class MaterialError(ValueError):
    """A natural task's file exists but cannot be read: the checks would run against less than the task holds."""


def _read_json(path: Path) -> Any:
    """The JSON value of ``path``, or None if it cannot be read (only where a missing or broken file hides nothing)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _material_json(path: Path) -> Any:
    """The JSON value of a natural task's file, None if there is no such file; :class:`MaterialError` if it exists but
    cannot be read or parsed (fail closed)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MaterialError(f"{path}: cannot be read as JSON ({exc.__class__.__name__})") from None


def task_population(task_dir: Path) -> str | None:
    """The population that ``task.json`` (else ``session.json``) records."""
    for name in ("task.json", "session.json"):
        d = _read_json(task_dir / name)
        if isinstance(d, dict) and isinstance(d.get("population"), str):
            return str(d["population"])
    return None


def is_natural_population(population: str | None) -> bool:
    return population is not None and (population == "natural" or population.startswith("natural:"))


def natural_task_dirs(tasks_root: Path) -> list[Path]:
    """Every task directory under ``tasks_root`` (the natural tasks root), by name: an accepted family, a rejected one,
    one whose compilation stopped half-way, one that holds a rejection record only. None is left out for what its
    records say or lack."""
    return sorted(d for d in Path(tasks_root).iterdir() if d.is_dir())


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


class SnapshotFiles:
    """The Python files of a task's base snapshot, read when first asked: whether an installed package's traceback frame
    is the natural repository's own code."""

    def __init__(self, base: Path | None) -> None:
        self.base = base
        self._by_name: dict[str, list[str]] | None = None
        self._packages: set[str] = set()  # the names of the snapshot's directories that hold a Python file

    def holds(self, frame_path: str) -> bool | None:
        """Whether a frame in an installed package (its path after ``site-packages/`` or ``dist-packages/``) is the
        repository's own code: the snapshot holds its file (as the end of a path in the snapshot), or its package (the
        first directory of that path) is the name of a directory of the snapshot that holds a Python file, so that a
        module the installed release has and the base lacks counts too. None when there is no snapshot to ask."""
        if self.base is None or not self.base.is_dir():
            return None
        if self._by_name is None:
            self._by_name = {}
            for f in self.base.rglob("*.py"):
                rel = f.relative_to(self.base).as_posix()
                self._by_name.setdefault(f.name, []).append(rel)
                if f.parent != self.base:
                    self._packages.add(f.parent.name)
        rel = _INSTALLED_PATH.split(frame_path.replace("\\", "/"))[-1]
        package, sep, _ = rel.partition("/")
        if sep and package in self._packages:
            return True
        name = rel.rsplit("/", 1)[-1]
        return any(p == rel or p.endswith("/" + rel) for p in self._by_name.get(name, ()))


def library_frames(text: str, own: Callable[[str], bool | None] | None = None) -> list[tuple[int, int]]:
    """The spans of ``text`` that are traceback boilerplate, with their line breaks, adjacent spans merged:

    * a frame of a Python traceback in the standard library (a path under ``lib/python3.x`` that is not an installed
      package's ``site-packages`` or ``dist-packages``, or a frozen module), or in an installed package of which ``own``
      says that it is not the natural repository's code (:meth:`SnapshotFiles.holds` is False): the ``File ...`` line, the
      source line after it and the ``^``/``~`` marker lines, each indented deeper than the ``File`` line;
    * the marker lines of every other frame;
    * of a frame of an installed package that is kept, its ``File`` line up to ``site-packages/`` (``dist-packages/``):
      that prefix is the same in every installed frame, so a window across it would match other packages' frames.

    A frame of an installed package that may be the repository's own code (``own`` is None, or says so) is kept from
    its package's path on: it holds the repository's file names and code."""
    spans: list[tuple[int, int]] = []

    def add(s: int, e: int) -> None:
        if spans and s <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], e))
        else:
            spans.append((s, e))

    for m in _FRAME.finditer(text):
        path = m.group(2)
        inst = _INSTALLED_PATH.search(path)
        installed = inst is not None
        drop = (bool(_STDLIB_PATH.search(path)) and not installed) or (installed and own is not None and own(path) is False)
        if inst is not None and not drop:
            add(m.start(), m.start(2) + inst.end())
        indent, end = len(m.group(1)), m.end()
        marks = -1  # where the marker lines start
        for k, line in enumerate(text[end + 1:end + 4001].split("\n")[:8]):  # the source line, then marker lines
            bare = line.rstrip("\r")
            deeper = bool(bare.strip()) and _indent(bare) > indent
            is_code = k == 0 and deeper and not _FRAME.fullmatch(bare) and not _MARKERS.fullmatch(bare)
            is_mark = deeper and bool(_MARKERS.fullmatch(bare))
            if not (is_code or is_mark):
                break
            if is_mark and marks < 0:
                marks = end + 1
            end += 1 + len(line)
        end = min(len(text), end + 1)  # the line break after the frame
        if drop:
            add(m.start(), end)
        elif marks >= 0:
            add(marks, end)
    return spans


def _generic_line(line: str, generic: frozenset[str] | set[str]) -> bool:
    """``line`` (whitespace collapsed, and also without a leading diff marker) is one of the ``generic`` lines and holds
    ``MIN_GENERIC_WORDS`` words."""
    n = _WS.sub(" ", line).strip()
    if len(_WORD.findall(n)) < MIN_GENERIC_WORDS:
        return False
    return n in generic or (n[0] in "+-" and n[1:].lstrip() in generic)


def boilerplate(text: str, own: Callable[[str], bool | None] | None = None,
                generic: frozenset[str] | set[str] = frozenset()) -> list[tuple[int, int]]:
    """The spans of ``text`` that are no thread's own text, with their line breaks, sorted and merged:

    * traceback boilerplate (:func:`library_frames`);
    * tool output that names no one (``_TOOL_LINE``): pytest's section banners, pip's resolver errors;
    * with ``generic`` (:func:`generic_lines` of a corpus written before any natural task existed), each line that the
      corpus held, if it has ``MIN_GENERIC_WORDS`` words: an import block, a common idiom or a pytest summary line in a
      diff hunk or an issue is no thread's own text, and the study's own files hold the same lines."""
    spans = list(library_frames(text, own))
    for m in _TOOL_LINE.finditer(text):
        spans.append((m.start(), min(len(text), m.end() + 1)))
    if generic:
        at = 0
        for line in text.splitlines(keepends=True):
            if _generic_line(line, generic):
                spans.append((at, at + len(line)))
            at += len(line)
    out: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def thread_segments(text: str, own: Callable[[str], bool | None] | None = None,
                    generic: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """``text`` without its boilerplate (:func:`boilerplate`), as the parts between the removed spans, so that no window
    spans one. Traceback frames and markers, tool banners and the generic lines are the same in many texts and name no
    one."""
    out, last = [], 0
    for s, e in boilerplate(text, own, generic):
        out.append(text[last:s])
        last = e
    out.append(text[last:])
    return [x for x in out if x.strip()]


def natural_texts(task_dir: Path) -> Iterator[str]:
    """Every session event's text (the issue, the PR body, the commit messages, the diff hunk, the review comment, the
    replies), and every quote of the task's contracts (``contracts/*.json``): a quote shorter than a window of its event
    is matched only as itself. :class:`MaterialError` if ``session.json`` or a contract exists but cannot be read."""
    session = _material_json(task_dir / "session.json")
    for e in (session or {}).get("events", []) if isinstance(session, dict) else []:
        if isinstance(e, dict) and isinstance(e.get("text"), str) and e["text"]:
            yield e["text"]
    for f in sorted((task_dir / "contracts").glob("*.json")) if (task_dir / "contracts").is_dir() else []:
        c = _material_json(f)
        for r in c.get("requirements", []) if isinstance(c, dict) else []:
            for ev in r.get("evidence", []) if isinstance(r, dict) else []:
                if isinstance(ev, dict) and isinstance(ev.get("quote"), str) and ev["quote"]:
                    yield ev["quote"]


def _title_body(title: Any, body: Any) -> str:
    """An issue's text as a session holds it (``ingest.github_pr``): the title, a blank line and the body."""
    t, b = (title or "").strip() if isinstance(title, str) else "", (body or "").strip() if isinstance(body, str) else ""
    return f"{t}\n\n{b}" if b else t


def screening_texts(path: str | Path) -> Iterator[tuple[int, str]]:
    """The texts of each comment in a screening text file (``scripts/screen_aidev.py --texts-out``: one JSON line per
    sampled comment, kept outside the repository), as ``(comment id, text)``: the comment, its linked issue (title and
    body), its PR's title and its diff hunk. ValueError on a line that is no such row."""
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise ValueError(f"{path}:{n}: not a JSON line") from None
        cid = row.get("comment_id") if isinstance(row, dict) else None
        if type(cid) is not int:
            raise ValueError(f"{path}:{n}: not a screening text row (no comment_id)")
        for text in (row.get("comment_body"), _title_body(row.get("issue_title"), row.get("issue_body")),
                     row.get("pr_title"), row.get("diff_hunk")):
            if isinstance(text, str) and text:
                yield cid, text


# ---------------------------------------------------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Repository:
    """A natural task's repository. ``owner`` is None when the ``{owner}`` rule masked it (the owner is a person, whose
    login the scan's ``--aidev-logins`` check covers); ``name`` is None when it holds the masked owner."""

    owner: str | None
    name: str | None
    task_ids: tuple[str, ...]

    @property
    def distinctive(self) -> bool:
        """The name holds a separator or a digit (``fx-widgets``), so it is no ordinary word."""
        return bool(self.name and re.search(r"[-_.\d]", self.name))


def parse_repository(url: str) -> tuple[str, str] | None:
    """``(owner, name)`` of a repository URL (``https://github.com/<owner>/<name>``, an API URL, a ``.git`` URL)."""
    u = urlsplit(url.strip())
    segs = [s for s in u.path.split("/") if s]
    if u.netloc.lower() == "api.github.com" and segs[:1] == ["repos"]:
        segs = segs[1:]
    if not u.netloc or len(segs) < 2:
        return None
    return segs[0], segs[1].removesuffix(".git")


def task_repository_urls(task_dir: Path) -> set[str]:
    """The repository URLs that the task's records hold (task.json, session.json, provenance.json, snapshot.json);
    :class:`MaterialError` if one of them exists but cannot be read."""
    urls: set[str] = set()
    for name in ("task.json", "session.json", "provenance.json", "snapshot.json"):
        d = _material_json(task_dir / name)
        if not isinstance(d, dict):
            continue
        for u in (d.get("repo_url"), (d.get("snapshot_source") or {}).get("repo_url") if isinstance(
                d.get("snapshot_source"), dict) else None):
            if isinstance(u, str) and u.strip():
                urls.add(u.strip())
    return urls


def repositories(task_dirs: Iterable[Path]) -> list[Repository]:
    """The distinct repositories of the tasks, each with the ids of its tasks."""
    by_key: dict[tuple[str | None, str | None], set[str]] = {}
    for td in task_dirs:
        for url in task_repository_urls(td):
            parsed = parse_repository(url)
            if parsed is None:
                continue
            owner, name = parsed
            key = (None if MASKED_OWNER in owner else owner, None if MASKED_OWNER in name else name)
            if key != (None, None):
                by_key.setdefault((key[0] and key[0].lower(), key[1] and key[1].lower()), set()).add(td.name)
    return [Repository(owner, name, tuple(sorted(ids))) for (owner, name), ids in sorted(
        by_key.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or ""))]


class RepositoryNames:
    """Where a text names a natural task's repository.

    * ``owner``: the owner in the URL form ``/<owner>/``, or right after a host as ``<host>/<owner>`` followed by a
      character that cannot continue the owner's name or by the end of the text (the owner's own page), in any case (an
      owner that is not masked: an organisation). ``//<owner>.<tld>``, a host that bears the owner's name, is no URL of
      the owner's account;
    * ``reference``: the name in a form that names a repository, in any case: ``<owner>/<name>``, or a URL path
      ``<host>/<account>/<name>`` (also ``<host>:<account>/<name>`` and ``api.github.com/repos/...``) with any account;
    * ``name``: the name as a whole word anywhere else (not inside a longer name: no letter, digit, ``_`` or ``-`` next
      to it, and no ``.`` before it), with ``bare`` or for a distinctive name (:attr:`Repository.distinctive`), which no
      ordinary word is.

    Wherever the name holds ``-``, ``_`` or ``.``, any of the three matches (``fx_widgets`` is the package of the
    repository ``fx-widgets``).
    """

    _URL_BEFORE = re.compile(rf"{_DOMAIN}[/:](?:repos/)?[A-Za-z0-9_.{{}}-]+/$")
    _HOST_BEFORE = re.compile(rf"(?<![A-Za-z0-9.-]){_DOMAIN}$")  # a host right before ``/<owner>``
    _CONTEXT = 256  # characters before a name that are read for its repository form

    def __init__(self, repos: Iterable[Repository]) -> None:
        self.repos = [r for r in repos if r.owner or r.name]
        self._word: dict[Repository, re.Pattern[str]] = {}
        self._owner: dict[Repository, re.Pattern[str]] = {}
        self._owner_before: dict[Repository, re.Pattern[str]] = {}
        self._prefilter: dict[Repository, str] = {}  # a lower-case part of the name that every match holds
        for r in self.repos:
            if r.name:
                parts = re.split(r"[-_.]", r.name)
                body = "[-_.]".join(map(re.escape, parts))
                self._word[r] = re.compile(rf"(?<![A-Za-z0-9_.-]){body}(?![A-Za-z0-9_-])", re.IGNORECASE)
                self._prefilter[r] = max(parts, key=len).lower()
            if r.owner:
                self._owner[r] = re.compile(rf"/{re.escape(r.owner)}(/|(?![A-Za-z0-9_-]))", re.IGNORECASE)
                self._owner_before[r] = re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(r.owner)}/$", re.IGNORECASE)

    def _reference(self, r: Repository, before: str) -> bool:
        """The text ``before`` a whole-word name ends in a form that names a repository: ``<owner>/`` or a URL's
        ``<host>/<account>/``."""
        return bool(self._URL_BEFORE.search(before) or (r.owner and self._owner_before[r].search(before)))

    def find(self, text: str, *, bare: bool) -> list[tuple[int, str, Repository]]:
        """Each match in ``text``: (offset, ``"owner"``, ``"reference"`` or ``"name"``, the repository), sorted."""
        low = _lower(text)
        out: list[tuple[int, str, Repository]] = []
        for r in self.repos:
            if r.owner and r.owner.lower() in low:
                for m in self._owner[r].finditer(text):
                    if m.group(1) == "/" or self._HOST_BEFORE.search(text, max(0, m.start() - self._CONTEXT), m.start()):
                        out.append((m.start(), "owner", r))
            if r.name and self._prefilter[r] in low:
                for m in self._word[r].finditer(text):
                    ref = self._reference(r, text[max(0, m.start() - self._CONTEXT):m.start()])
                    if ref or bare or r.distinctive:
                        out.append((m.start(), "reference" if ref else "name", r))
        return sorted(out, key=lambda x: (x[0], x[1], x[2].task_ids))


# ---------------------------------------------------------------------------------------------------------------------
# Code
# ---------------------------------------------------------------------------------------------------------------------


def code_line(line: str, *, min_len: int = MIN_CODE_LINE) -> str | None:
    """The line with its whitespace collapsed and stripped, if it is long enough to tell apart (``min_len`` characters,
    two words with a letter and a word of ``MIN_CODE_WORD`` characters: ``dx, dy = x1 - x0, y1 - y0`` is too generic);
    else None."""
    if len(line) < min_len:  # collapsing whitespace only shortens a line
        return None
    n = " ".join(line.split())  # as _WS.sub(" ", line).strip(): both split at the same (Unicode) whitespace
    if len(n) < min_len:
        return None
    words = _WORD.findall(n)
    if max(map(len, words), default=0) < MIN_CODE_WORD:
        return None
    lettered = 0
    for w in words:
        if _lettered(w):
            lettered += 1
            if lettered == 2:
                return n
    return None


def patch_lines(patch: str) -> Iterator[str]:
    """The added, removed and context lines of a unified diff, without their markers."""
    for line in patch.splitlines():
        if not line or line.startswith(_DIFF_HEADERS):
            continue
        yield line[1:] if line[0] in "+- " else line


def _node_ids(obj: Any) -> Iterator[str]:
    """Every string in a JSON value that is a pytest node id (holds ``::``)."""
    if isinstance(obj, str):
        if "::" in obj:
            yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _node_ids(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _node_ids(v)


def _text_lines(path: Path, binary: list[Path] | None = None) -> Iterator[str]:
    """The lines of a file of code, whatever its size. :class:`MaterialError` if it cannot be read (fail closed); a
    file with a NUL byte holds no line of code and is added to ``binary`` instead, so that the checks can say so."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise MaterialError(f"{path}: cannot be read ({exc.strerror or exc.__class__.__name__})") from None
    if b"\0" in data:
        if binary is not None:
            binary.append(path)
        return
    yield from data.decode("utf-8", errors="replace").splitlines()


def _verifier_files(task_dir: Path) -> Iterator[Path]:
    vdir = task_dir / "verifiers"
    for f in sorted(vdir.rglob("*")) if vdir.is_dir() else []:
        if f.is_file() and not f.is_symlink():
            yield f


def task_check_ids(task_dir: Path) -> Iterator[str]:
    """The check ids of a natural task's verifiers (every pytest node id in ``spec.json``, ``check_ids.json``, B1's
    ``selection.json`` ...), each also without the directories of its file (``test_mod.py::test_add`` for
    ``tests/test_mod.py::test_add``), as a text may cite it so."""
    for f in _verifier_files(task_dir):
        if f.suffix == ".json":
            for nid in _node_ids(_material_json(f)):
                yield nid
                path, sep, rest = nid.partition("::")
                if "/" in path:
                    yield path.rsplit("/", 1)[1] + sep + rest


def task_code_lines(task_dir: Path, base_dir: Path | None = None, *, binary: list[Path] | None = None) -> Iterator[str]:
    """A natural task's code lines: the lines of its candidates' patches and of its verifiers' files (B1's overlay of
    upstream tests, the generated tests), and, with ``base_dir`` (the base snapshot), the lines of the base's Python
    files (:func:`base_code_lines`). Lines that :func:`code_line` refuses are left out; :class:`MaterialError` for a
    candidate or file that cannot be read; a binary file is added to ``binary`` (:func:`_text_lines`)."""
    for f in sorted((task_dir / "candidates").glob("*.json")) if (task_dir / "candidates").is_dir() else []:
        c = _material_json(f)
        if isinstance(c, dict) and isinstance(c.get("patch"), str):
            yield from filter(None, map(code_line, patch_lines(c["patch"])))
    for f in _verifier_files(task_dir):
        if f.suffix != ".json":
            yield from filter(None, map(code_line, _text_lines(f, binary)))
    if base_dir is not None:
        yield from base_code_lines(base_dir, binary=binary)


def base_code_lines(base_dir: Path, *, binary: list[Path] | None = None) -> Iterator[str]:
    """The code lines of a base snapshot: the lines of all its Python files (``CODE_SUFFIXES``, whatever their size)
    that :func:`code_line` keeps. :class:`MaterialError` for a file that cannot be read; a binary file is added to
    ``binary``."""
    if base_dir.is_dir():
        for f in sorted(base_dir.rglob("*")):
            if f.suffix in CODE_SUFFIXES and f.is_file() and not f.is_symlink():
                yield from filter(None, map(code_line, _text_lines(f, binary)))


def task_code(task_dir: Path, base_dir: Path | None = None) -> Iterator[str]:
    """A natural task's code lines (:func:`task_code_lines`) and check ids (:func:`task_check_ids`)."""
    yield from task_code_lines(task_dir, base_dir)
    yield from task_check_ids(task_dir)


def generic_lines(texts: Iterable[str]) -> frozenset[str]:
    """The lines of ``texts`` that hold ``MIN_GENERIC_WORDS`` words, as :class:`CodeLines` and :func:`boilerplate`
    compare them (whitespace collapsed, stripped): as written, as their backslash escapes decode them (a patch, a test or
    a transcript inside a JSON string) and, after a diff marker, without it. From a corpus written before any natural
    task existed, these are the idioms and tool output that natural texts and upstream code share with the study's own
    files."""
    out: set[str] = set()
    for text in texts:
        decoded = _decoded(text, _ESCAPE, _unescape) if "\\" in text else None
        for t in (text,) if decoded is None else (text, decoded.text):
            for line in t.splitlines():
                n = _WS.sub(" ", line).strip()
                if len(_WORD.findall(n)) >= MIN_GENERIC_WORDS:
                    out.add(n)
                    if n[0] in "+-":
                        out.add(n[1:].lstrip())
    return frozenset(out)


_LINE_COUNTS: dict[int, tuple[frozenset[str] | set[str], dict[str, int]]] = {}  # id(generic) -> (generic, counts)


def _line_counts(generic: frozenset[str] | set[str]) -> dict[str, int]:
    """For each word, the lines of ``generic`` that hold it; computed once per corpus object (a few are kept)."""
    hit = _LINE_COUNTS.get(id(generic))
    if hit is not None and hit[0] is generic:
        return hit[1]
    counts: dict[str, int] = {}
    for line in generic:
        for w in set(_WORD.findall(line)):
            counts[w] = counts.get(w, 0) + 1
    if len(_LINE_COUNTS) >= 4:
        _LINE_COUNTS.clear()
    _LINE_COUNTS[id(generic)] = (generic, counts)
    return counts


def distinctive_line(line: str, counts: dict[str, int]) -> bool:
    """Whether a base snapshot's code line names something of its own: one of its words of ``MIN_CODE_WORD`` characters
    or more is in at most ``BASE_RARE_LINES`` lines of the corpus written before any natural task (``counts``: the
    lines of :func:`generic_lines` that hold each word). A line of words that the study's own files use throughout
    (``except (KeyError, ValueError):``, ``results: dict[str, Any] = {``) is an idiom that a whole repository's hundreds
    of thousands of lines share with many others; it tells no repository apart. The lines of a task's patches and
    verifiers are not filtered so."""
    return any(len(w) >= MIN_CODE_WORD and counts.get(w, 0) <= BASE_RARE_LINES for w in _WORD.findall(line))


class CodeLines:
    """Where a text holds a natural task's code line or check id (:func:`task_code`), after its whitespace is collapsed,
    with no word character joined to either end; the text is also read in the views of :class:`TextWindows`. Case
    counts. Lines in ``generic`` (common idioms, such as ``from pathlib import Path``) are left out; with ``require``,
    only a text that holds that string in some view is searched (``::`` for check ids).

    Each line is indexed by one of its words (a run of letters, digits and underscores): of its words of 4 characters
    or more (else of all), the one in the fewest lines of ``generic`` (the study's own corpus, which the searched texts
    resemble), the longest of those; it is looked up at each occurrence, as a whole word, of such a word in the searched
    text. The choice of word changes the speed only: every occurrence of a line holds each of its words."""

    def __init__(self, needles: Iterable[tuple[str, str]], *, generic: frozenset[str] | set[str] = frozenset(),
                 require: str = "") -> None:
        self._index: dict[str, list[tuple[str, int, str]]] = {}  # word -> (line, offset of the word in it, label)
        self._require = require
        common = _line_counts(generic)
        seen: set[tuple[str, str]] = set()
        for label, needle in needles:
            n = " ".join(needle.split())
            if not n or n in generic or (label, n) in seen or require not in n:
                continue
            words = list(_WORD.finditer(n))
            if not words:
                continue
            seen.add((label, n))
            w = min(words, key=lambda m: (len(m.group()) < 4, common.get(m.group(), 0), -len(m.group()), m.start()))
            self._index.setdefault(w.group(), []).append((n, w.start(), label))
        self.n_needles = len(seen)
        self.labels = frozenset(label for label, _ in seen)  # the labels that have a line or id to look for
        self._keys = frozenset(self._index)

    def find(self, text: str, views: Sequence[_View] | None = None) -> list[tuple[int, str]]:
        """Each match in ``text``: (offset in ``text``, the label of the code), sorted; the code is not returned.
        ``views``: ``text_views(text)``, if already computed."""
        found: dict[tuple[int, str], None] = {}
        if not self._index:
            return []
        index = self._index
        for view in views if views is not None else _views(text):
            if self._require and self._require not in view.text:
                continue
            nv = _Normalised(view, lower=False)
            t = nv.text
            n = len(t)
            pieces = _WORD_SPLIT.split(t)  # text between words, word, text between words, ..., text after the last word
            words = pieces[1::2]
            present = self._keys.intersection(words)  # the index words that the text holds as words
            if not present:
                continue
            ends = list(accumulate(map(len, pieces)))  # word j starts where piece 2j ends
            for j in compress(range(len(words)), map(present.__contains__, words)):
                k = ends[2 * j]
                for needle, at, label in index[words[j]]:
                    p, e = k - at, k - at + len(needle)
                    if p < 0 or not t.startswith(needle, p):
                        continue
                    if (p > 0 and _wordchar(needle[0]) and _wordchar(t[p - 1])) or (
                            e < n and _wordchar(needle[-1]) and _wordchar(t[e])):
                        continue
                    found[(nv.to_source(p), label)] = None
        return sorted(found)


@dataclass(frozen=True)
class NaturalMaterial:
    """The thread-text windows and short texts, the repositories, the code lines (``code``: patches and verifiers;
    ``base_code``: the base snapshots' distinctive lines, :func:`distinctive_line`) and the check ids of every task
    directory under a natural tasks root, and the windows and short texts of the screening texts given (``screened``:
    the comment ids they hold). ``base_snapshots``: ``(task id, base snapshot directory, code lines read)`` of each task
    with a base snapshot; ``binary``: the files of the verifiers and base snapshots not read as code because they hold
    a NUL byte."""

    task_ids: tuple[str, ...]
    windows: TextWindows
    repos: RepositoryNames
    code: CodeLines = field(default_factory=lambda: CodeLines(()))
    check_ids: CodeLines = field(default_factory=lambda: CodeLines(()))
    screened: frozenset[int] = frozenset()
    base_code: CodeLines = field(default_factory=lambda: CodeLines(()))
    base_snapshots: tuple[tuple[str, Path, int], ...] = ()
    binary: tuple[Path, ...] = ()

    def base_snapshot(self, task_id: str) -> tuple[Path, int] | None:
        """The base snapshot directory read for ``task_id`` and the code lines read from it, or None."""
        return next(((p, n) for t, p, n in self.base_snapshots if t == task_id), None)

    @classmethod
    def load(cls, tasks_root: str | Path, *, screening: Iterable[str | Path] = (),
             generic: frozenset[str] | set[str] = frozenset(), snapshots_root: str | Path | None = None,
             distinctive_base: bool = True) -> NaturalMaterial:
        """Every task directory under ``tasks_root`` (:func:`natural_task_dirs`) and the screening text files
        ``screening`` (:func:`screening_texts`). ``generic``: the lines of a corpus written before any natural task
        existed (:func:`generic_lines`), which are cut out of the texts (:func:`boilerplate`) and are no code line
        (:class:`CodeLines`). ``snapshots_root``: the tasks' base snapshots (``<root>/<task id>``; default ``snapshots``
        beside ``tasks_root``, as in ``data/natural``), whose Python files give code lines (:func:`base_code_lines`) and
        tell an installed package's traceback frame of the repository's own code from a library's
        (:func:`library_frames`); with ``distinctive_base`` (the default), only their lines that name something of
        their own (:func:`distinctive_line`), else all of them (but the generic lines).

        Each text gives its segments (:func:`thread_segments`): the windows of each, and each segment with no window of
        words matched whole (:class:`TextWindows`). FileNotFoundError without a task directory, or when no directory
        under ``tasks_root`` holds a ``task.json`` or ``session.json`` (a root one level too high or too low);
        :class:`MaterialError` on a task file that exists but cannot be read, and for a task whose ``snapshot.json``
        records a base snapshot that is missing or yields no code line; ValueError on a screening text file that cannot
        be read."""
        root = Path(tasks_root)
        if not root.is_dir():
            raise FileNotFoundError(f"no natural tasks directory at {root}")
        dirs = natural_task_dirs(root)
        if not dirs:
            raise FileNotFoundError(f"{root} holds no task directory")
        if not any((d / "task.json").is_file() or (d / "session.json").is_file() for d in dirs):
            raise FileNotFoundError(f"{root} holds no natural task: none of its {len(dirs)} directories holds a task.json "
                                    "or session.json (the natural tasks root is data/natural/tasks)")
        snaps = Path(snapshots_root) if snapshots_root is not None else root.parent / "snapshots"
        bases: dict[str, Path] = {}
        for d in dirs:
            if (snaps / d.name).is_dir():
                bases[d.name] = snaps / d.name
            elif (d / "snapshot.json").exists():
                raise MaterialError(f"{d.name}: no base snapshot at {snaps / d.name}, though its snapshot.json records one")
        texts: list[tuple[str, str]] = []

        def add(label: str, text: str, own: Callable[[str], bool | None] | None = None) -> None:
            texts.extend((label, s) for s in thread_segments(text, own, generic))

        for d in dirs:
            own = SnapshotFiles(snaps / d.name).holds
            for t in natural_texts(d):
                add(d.name, t, own)
        screened: set[int] = set()
        for path in screening:
            try:
                rows = list(screening_texts(path))
            except OSError as exc:
                raise ValueError(f"{path}: {exc.strerror or exc}") from None
            for cid, text in rows:
                screened.add(cid)
                add(f"screened comment {cid}", text)
        binary: list[Path] = []
        code = CodeLines(((d.name, x) for d in dirs for x in task_code_lines(d, binary=binary)), generic=generic)
        ids = CodeLines(((d.name, x) for d in dirs for x in task_check_ids(d)), require="::")
        read: dict[str, int] = {}

        def base_lines() -> Iterator[tuple[str, str]]:
            for tid, base in bases.items():
                read[tid] = 0
                for x in base_code_lines(base, binary=binary):
                    read[tid] += 1
                    yield tid, x

        counts = _line_counts(generic)
        base_code = CodeLines(((t, x) for t, x in base_lines() if not distinctive_base or distinctive_line(x, counts)),
                              generic=generic)
        for tid, base in bases.items():
            if not read[tid] and (root / tid / "snapshot.json").exists():
                raise MaterialError(f"{tid}: no code line could be read from its base snapshot at {base} (no Python file, "
                                    "or none with a line long enough to tell apart)")
        return cls(tuple(d.name for d in dirs), TextWindows(texts), RepositoryNames(repositories(dirs)), code, ids,
                   frozenset(screened), base_code, tuple((t, b, read[t]) for t, b in bases.items()), tuple(binary))


def line_number(text: str, offset: int) -> int:
    """The 1-based line of ``text`` that holds ``offset``, counting lines as ``str.splitlines`` does."""
    return len((text[:max(0, offset)] + "x").splitlines())
