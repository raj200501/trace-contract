"""The string semantics of Claude Code's ``Edit`` tool, shared by both transcript replays (D47, D51).

:mod:`tracecontract.ingest.replay` and :mod:`tracecontract.reconstruction` both apply a recorded
``Edit`` or ``MultiEdit`` call with :func:`apply_edits`, so they cannot disagree about an edit.
The tool (as read from an installed build's bundle; earlier builds may differ in the
normalisation steps, which is why every edit that needs one is flagged):

* reads the file with CRLF line breaks as LF and writes it back with CRLF
  (``line_endings_converted``);
* looks ``old_string`` up as given, else with curly quotes read as straight ones in both
  strings, and then uses the file's own text at that place (``quote_normalised``); straight
  quotes in ``new_string`` then take the file's curly style;
* refuses an ``old_string`` that occurs more than once unless ``replace_all`` is set,
  counting occurrences as ``str.count`` does (non-overlapping; the tool's ``split`` count);
* with an empty ``new_string``, also removes the line break that follows ``old_string``
  when the file has one there;
* with an empty ``old_string``, creates the file, or fills one that holds only whitespace.

Escape-sequence variants (``\\uXXXX`` in ``old_string``), which newer builds also try, are not
replayed: such an edit reads as ``absent``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

LEFT_SINGLE, RIGHT_SINGLE, LEFT_DOUBLE, RIGHT_DOUBLE = "‘", "’", "“", "”"
_STRAIGHT = str.maketrans({LEFT_SINGLE: "'", RIGHT_SINGLE: "'", LEFT_DOUBLE: '"', RIGHT_DOUBLE: '"'})
_OPENS_AFTER = frozenset(" \t\n\r([{—–")  # a quote after these (or at the start) opens

Edit = tuple[str, str, bool]  # (old_string, new_string, replace_all)


def normalize_quotes(text: str) -> str:
    """Curly single and double quotes as straight ones (one character for one, so offsets hold)."""
    return text.translate(_STRAIGHT)


def actual_old_string(text: str, old: str) -> str | None:
    """The file's own text that ``old`` matches: ``old`` itself, else the span it matches with quotes normalised."""
    if old in text:
        return old
    k = normalize_quotes(text).find(normalize_quotes(old))
    return text[k:k + len(old)] if k >= 0 else None


def _curly(text: str, straight: str, opening: str, closing: str, *, apostrophe: bool) -> str:
    chars, out = list(text), []
    for i, c in enumerate(chars):
        if c != straight:
            out.append(c)
        elif apostrophe and 0 < i < len(chars) - 1 and chars[i - 1].isalpha() and chars[i + 1].isalpha():
            out.append(closing)  # an apostrophe inside a word
        else:
            out.append(opening if i == 0 or chars[i - 1] in _OPENS_AFTER else closing)
    return "".join(out)


def preserve_quote_style(old: str, actual: str, new: str) -> str:
    """``new`` with straight quotes made curly, as the tool does when ``old`` matched only with quotes normalised."""
    if old == actual:
        return new
    if LEFT_DOUBLE in actual or RIGHT_DOUBLE in actual:
        new = _curly(new, '"', LEFT_DOUBLE, RIGHT_DOUBLE, apostrophe=False)
    if LEFT_SINGLE in actual or RIGHT_SINGLE in actual:
        new = _curly(new, "'", LEFT_SINGLE, RIGHT_SINGLE, apostrophe=True)
    return new


def apply_edit(text: str | None, old: str, new: str, replace_all: bool = False) -> tuple[str | None, str | None]:
    """Apply one edit as the tool does; returns ``(text, note)``.

    On a refusal the text is None and the note is ``file_missing``, ``file_exists``, ``absent``
    or ``not_unique``. A match found only with quotes normalised succeeds with the note
    ``quote_normalised``.
    """
    if text is None:
        return (new, None) if old == "" else (None, "file_missing")
    if old == "":
        return (new, None) if text.strip() == "" else (None, "file_exists")
    actual = actual_old_string(text, old)
    if actual is None:
        return None, "absent"
    if not replace_all and text.count(actual) > 1:
        return None, "not_unique"
    note = None if actual == old else "quote_normalised"
    new = preserve_quote_style(old, actual, new)
    if new == "" and not actual.endswith("\n") and actual + "\n" in text:
        actual += "\n"
    return (text.replace(actual, new) if replace_all else text.replace(actual, new, 1)), note


@dataclass(frozen=True)
class Applied:
    """The outcome of one ``Edit`` or ``MultiEdit`` call (:func:`apply_edits`)."""

    text: str | None  # the new content; None when the tool would have refused the call
    problem: str | None = None  # the refused edit's note (file_missing, file_exists, absent, not_unique)
    failed_at: int | None = None  # the refused edit's position in the call
    notes: tuple[str, ...] = ()  # quote_normalised (per edit) and line_endings_converted (once)


def apply_edits(text: str | None, edits: Sequence[Edit]) -> Applied:
    """Apply a call's edits in order (one for ``Edit``, several for ``MultiEdit``), with the tool's line endings."""
    crlf = text is not None and "\r\n" in text
    notes: list[str] = []
    for k, (old, new, replace_all) in enumerate(edits):
        if crlf and text is not None and "\r" not in old:
            text = text.replace("\r\n", "\n")
        text, note = apply_edit(text, old, new, replace_all)
        if text is None:
            return Applied(None, note, k, tuple(notes))
        if note:
            notes.append(note)
    if crlf and text is not None and "\r\n" not in text:
        text = text.replace("\n", "\r\n")
        notes.append("line_endings_converted")
    return Applied(text, notes=tuple(notes))


def edits_of(tool: str, tool_input: Mapping[str, Any] | None) -> list[Edit]:
    """The ``(old_string, new_string, replace_all)`` edits of an ``Edit`` or ``MultiEdit`` call's input."""
    ti = tool_input or {}
    items = ti.get("edits") if tool == "MultiEdit" else [ti]
    return [(str(e.get("old_string", "")), str(e.get("new_string", "")), bool(e.get("replace_all")))
            for e in (items if isinstance(items, list) else []) if isinstance(e, Mapping)]
