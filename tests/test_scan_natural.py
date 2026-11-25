"""The natural checks of ``scripts/scan_tracked_files.py --natural-texts`` (build plan WP-H; protocol §17.4, decision log
D47) and their matchers (``tracecontract.natural_privacy``).

The natural tasks here are synthetic: the layout of tests/natural_task_layout.py (NP-90, whose repository's owner is
masked), a hand-written NP-91 with an organisation as owner, a base snapshot holding its own package, and texts in
the forms the checks must read (short comments, a CJK text, a list of short lines, traceback frames), NP-92 (a family
whose compilation stopped half-way: no task.json, a session without a population), NP-93 (a rejection record only)
and NP-95 (short texts: a 21-character, 3-word review comment, a 37-character, 5-word reply, an issue that is long only
by its traceback, a contract quote shorter than a window). NP-90's base snapshot gets a line of its own in the tests of
the base-snapshot check, and NP-97 (short comments with code and an accent) is added in the tests of the LaTeX and NFD
forms. The screening texts and AIDev files are synthetic too. Every planted string is synthetic. The last test runs the
scan on the repository itself against its own natural tasks, where they exist (``data/natural/tasks`` is git-ignored).
Not research evidence.
"""

from __future__ import annotations

import contextlib
import html
import importlib.util
import io
import json
import random
import re
import shutil
import unicodedata
from pathlib import Path
from urllib.parse import quote

import pytest
from natural_task_layout import (
    B1_CHECKS,
    COMMENT_TEXT,
    ISSUE_TEXT,
    REFERENCE_TEST,
    REPLY_TEXT,
    build_natural_task,
)

from tracecontract import natural_privacy as npv

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


scan = _load("scan_tracked_files")

LIB_FRAME = ('  File "/usr/local/lib/python3.12/asyncio/tasks.py", line 514, in wait_for\n'
             "    return await fut\n           ^^^^^^^^^\n")
USER_FRAME = '  File "/srv/fx-app/fx_app/render.py", line 10, in render\n    raise RenderError("widget gallery offline")\n'
# A frame of the repository's own package as installed (its base snapshot holds the file), and one of an installed
# library that the snapshot does not hold.
OWN_FRAME = ('  File "/opt/venv/lib/python3.12/site-packages/fx_widgets/gallery.py", line 88, in paint\n'
             "    self.canvas.draw_thumbnail(widget, scale=self.zoom_level)\n")
SITE_LIB_FRAME = ('  File "/opt/venv/lib/python3.12/site-packages/fxthirdparty/loop.py", line 7, in run\n'
                  "    return callback(*arguments)\n")
# A standard-library File line with no source line, followed by prose at the same indentation.
BARE_FILE = 'File "/usr/lib/python3.12/json/decoder.py", line 3\n'
AFTER_BARE = "The gallery stays blank for every widget without a thumbnail image."
LONG_PATH = "fx_app/gallery/rendering/pipeline/stage_two/render_queue_worker.py"
NP91_ISSUE = ("Widgets stop rendering after the upgrade. Open the gallery page, pick any widget, then press render "
              "twice.\n\nTraceback (most recent call last):\n" + LIB_FRAME + USER_FRAME + OWN_FRAME + SITE_LIB_FRAME
              + f"\nThe worker that fails is {LONG_PATH} for reference.\n" + "-" * 70 + "\n" + BARE_FILE + AFTER_BARE + "\n")
NP91_QUOTE = "keep the legacy gallery layout as the default for every existing account"  # only in the contract
# A person's texts in other forms: a list of short lines, a text in a script written without spaces (65 characters,
# no window of words), a short comment in that script, and a two-word comment.
LIST_TEXT = "Steps to see it:\n- open the gallery\n- pick the oldest widget\n- press render twice\n- watch the blank page"
CJK_TEXT = "画廊页面在升级之后完全无法渲染任何组件请先打开画廊然后任选一个组件连续点击两次渲染按钮页面就会变成空白并且控制台里没有任何错误信息"
CJK_SHORT = "请把缩放比例默认设为一"
TWO_WORDS = "Looks good"
AGENT_SHORT = "Apply the review suggestion"  # an agent's commit message: too short for a window, matched whole
DASHES = "-" * 75
UPSTREAM_LINE = "assert add(None, 2) == 2 and add(2, None) == 2"  # a line of NP-90's reference patch and B1 overlay
# NP-95's short texts, in the shapes of two accepted families' correction comments (synthetic): 21 characters and 3
# words, 37 characters and 5 words, with characters that JSON and HTML escape.
SHORT_21 = "Don't mutate defaults"
SHORT_37 = 'Swap "thumbnails" for naïve previews.'
OWN_SENTENCE = "Rendering crashes on every save."  # NP-95's issue: this sentence, then a standard-library traceback
NP95_ISSUE = (f"{OWN_SENTENCE}\n\nTraceback (most recent call last):\n" + LIB_FRAME
              + '  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 691, in run_until_complete\n'
              "    return future.result()\n")
SHORT_QUOTE = "keep the zoom slider"  # a contract quote shorter than a window, from NP-95's long reply
NP95_REPLY = ("The new gallery is fine, but please keep the zoom slider where it was, since several of our "
              "screenshots in the handbook show it in the toolbar.")
HALF_BUILT = "Widgets flicker when the zoom changes twice in a row; the second change wins and the first is lost."
HALF_BUILT_CHECK = "tests/test_flicker.py::test_second_zoom_change_wins"


def _np91(root: Path) -> None:
    td = root / "data" / "natural" / "tasks" / "NP-91"
    (td / "contracts").mkdir(parents=True)
    url = "https://github.com/fx-org/fx-widgets"
    (td / "task.json").write_text(json.dumps({"task_id": "NP-91", "population": "natural:pr-review",
                                              "snapshot_source": {"repo_url": url, "commit": "1" * 40}}))
    events = [("issue", "human", NP91_ISSUE), ("commit/1", "agent", "Initial plan"), ("commit/2", "agent", AGENT_SHORT),
              ("review/1", "human", CJK_SHORT), ("reply/1", "human", LIST_TEXT), ("reply/2", "human", CJK_TEXT),
              ("reply/3", "human", TWO_WORDS)]
    (td / "session.json").write_text(json.dumps({
        "session_id": "s91", "population": "natural:pr-review", "repo_url": url,
        "events": [{"event_id": f"s91/{e}", "author": a, "text": t} for e, a, t in events]}, ensure_ascii=False))
    (td / "contracts" / "full_session.json").write_text(json.dumps({"requirements": [
        {"req_id": "R1", "evidence": [{"event_id": "s91/issue", "start": 0, "end": len(NP91_QUOTE), "quote": NP91_QUOTE}]}]}))
    snap = root / "data" / "natural" / "snapshots" / "NP-91" / "src" / "fx_widgets"
    snap.mkdir(parents=True)
    (snap / "gallery.py").write_text("def paint(self, widget):\n    return widget\n")


def _np95(root: Path) -> None:
    td = root / "data" / "natural" / "tasks" / "NP-95"
    (td / "contracts").mkdir(parents=True)
    (td / "task.json").write_text(json.dumps({"task_id": "NP-95", "population": "natural:pr-review"}))
    events = [("issue", "human", NP95_ISSUE), ("review/1", "human", SHORT_21), ("reply/1", "human", SHORT_37),
              ("reply/2", "human", NP95_REPLY)]
    (td / "session.json").write_text(json.dumps({
        "session_id": "s95", "population": "natural:pr-review",
        "events": [{"event_id": f"s95/{e}", "author": a, "text": t} for e, a, t in events]}, ensure_ascii=False))
    at = NP95_REPLY.index(SHORT_QUOTE)
    (td / "contracts" / "full_session.json").write_text(json.dumps({"requirements": [{"req_id": "R1", "evidence": [
        {"event_id": "s95/reply/2", "start": at, "end": at + len(SHORT_QUOTE), "quote": SHORT_QUOTE}]}]}))


def _half_built(tasks: Path) -> None:
    """NP-92, whose compilation stopped half-way: no task.json, a session that records no population, and B1's
    selection; NP-93, a rejection record only."""
    td = tasks / "NP-92"
    (td / "verifiers" / "repo_tests").mkdir(parents=True)
    (td / "session.json").write_text(json.dumps({"session_id": "s92", "events": [
        {"event_id": "s92/review/1", "author": "human", "text": HALF_BUILT}]}))
    (td / "verifiers" / "repo_tests" / "selection.json").write_text(json.dumps({"selected": [HALF_BUILT_CHECK]}))
    (tasks / "NP-93").mkdir()
    (tasks / "NP-93" / "rejection.json").write_text(json.dumps({"task_id": "NP-93", "reason": "fetch over the caps"}))


@pytest.fixture
def tasks_root(tmp_path: Path) -> Path:
    """NP-90 (the layout's task), NP-91 (an organisation's repository, a contract quote), NP-92 and NP-93 (half built,
    rejection only) and NP-95 (short texts), under one tasks root."""
    nt = build_natural_task(tmp_path, index=False)
    _np91(tmp_path)
    _half_built(nt.tasks_root)
    _np95(tmp_path)
    return nt.tasks_root


@pytest.fixture
def natural(tasks_root: Path) -> npv.NaturalMaterial:
    return scan.natural_material(tasks_root)


def _report(text: str, where: str, natural, path: str | None = "") -> tuple[int, str]:
    """scan_natural's count and printed findings for ``text`` at ``where`` (also its path, unless ``path`` is given)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        n = scan.scan_natural(text, where, where if path == "" else path, natural)
    return n, buf.getvalue()


def lettered(w: str) -> bool:
    return any(c.isalpha() for c in w)


def _pieces(text: str, size: int = 20) -> list[str]:
    t = " ".join(text.split())
    return [t[i:i + size] for i in range(0, max(1, len(t) - size), 7)]


def test_planted_window_is_found_by_location_only(natural, capsys):
    assert natural.task_ids == ("NP-90", "NP-91", "NP-92", "NP-93", "NP-95")
    text = "# Run notes\n\nThe reviewer wrote: " + COMMENT_TEXT[3:80] + " and more.\n"
    where = "results/runs/natural-fx/analysis.md"
    assert scan.scan_natural(text, where, where, natural) == 1
    out = capsys.readouterr().out
    assert out == f"{where}:3: natural text window (NP-90)\n"
    assert not any(p.lower() in out.lower() for p in _pieces(COMMENT_TEXT))
    # Inside a JSON string (escaped line breaks), and with markup between the words (the 8-word windows).
    blob = json.dumps({"note": "x", "issue": ISSUE_TEXT}, indent=1)
    assert scan.scan_natural(blob, "data/x.json", "data/x.json", natural) == 1
    assert capsys.readouterr().out == "data/x.json:3: natural text window (NP-90)\n"
    marked = "**This** handles a *missing* first argument `only`: add"
    assert scan.scan_natural(marked, "docs/a.md", "docs/a.md", natural) == 1
    assert "docs/a.md:1: natural text window (NP-90)" in capsys.readouterr().out
    # A contract quote of NP-91 that no session event holds.
    assert scan.scan_natural(f"<p>{NP91_QUOTE.upper()}</p>", "results/r.html", "results/r.html", natural) == 1
    assert capsys.readouterr().out == "results/r.html:1: natural text window (NP-91)\n"


def test_what_is_no_window(natural, capsys):
    """A window inside one token, rules of dashes and library traceback frames are not windows."""
    for text in (f'"path": "{LONG_PATH}",', DASHES, "# " + DASHES + "\n", LIB_FRAME, "Traceback (most recent call last):",
                 SITE_LIB_FRAME):
        assert scan.scan_natural(text, "results/x.md", "results/x.md", natural) == 0, text
    assert scan.scan_natural(f"The worker that fails is {LONG_PATH} for", "docs/x.md", "docs/x.md", natural) == 1
    assert scan.scan_natural(USER_FRAME, "docs/x.md", "docs/x.md", natural) == 1  # a frame of the project's own code
    capsys.readouterr()


def test_a_short_comment_is_matched_whole(natural):
    """A text with no window (here the reviewer's reply of NP-90, 36 characters, NP-91's short comment in a script
    written without spaces, and an agent's commit message) is found when all its words are copied in a row, wherever
    the copy lies."""
    for where in ("docs/case_studies.md", "results/runs/natural-pr-v1/analysis.md", "paper/sections/natural.tex",
                  "src/tracecontract/x.py"):
        n, out = _report(f'In the case study the reviewer then adds: "{REPLY_TEXT}"\n', where, natural)
        assert (n, out) == (1, f"{where}:1: natural short text (NP-90)\n"), where
    prompt = json.dumps({"agent_id": "a1", "prompt": f"Context.\nThe reviewer replied: {REPLY_TEXT.upper()} Go on."})
    assert _report(prompt, "experiments/prompts/natural/agent_prompts_natural.jsonl", natural)[0] == 1
    assert _report(f"评审意见：{CJK_SHORT}。", "docs/case_studies.md", natural) == (
        1, "docs/case_studies.md:1: natural short text (NP-91)\n")
    assert _report(f"The agent's second commit: {AGENT_SHORT}.", "docs/case_studies.md", natural) == (
        1, "docs/case_studies.md:1: natural short text (NP-91)\n")
    # Not matched: the words not in a row, and texts below the minimum (a two-word comment, a two-word commit message).
    for text in ("And add(None, None) should not return 0.", f"they said {TWO_WORDS} twice", "Initial plan"):
        assert _report(text, "results/runs/natural-pr-v1/analysis.md", natural)[0] == 0, text


@pytest.mark.parametrize("comment", [SHORT_21, SHORT_37])
def test_short_texts_in_the_shapes_of_the_correction_comments(natural, comment):
    """A 21-character, 3-word review comment and a 37-character, 5-word reply (the shapes of two accepted families'
    correction comments) are found as written, in another case and spacing, JSON-escaped (also as ASCII, and inside
    a JSON string inside a JSON string) and HTML-escaped, in every directory; never repeated in the finding."""
    assert len(comment) in (21, 37) and len(comment.split()) in (3, 5)
    spaced = "\n  ".join(comment.upper().split())
    forms = [f"The reviewer: {comment}\n", f"The reviewer: {spaced}\n", json.dumps({"q": comment}) + "\n",
             json.dumps({"q": comment}, ensure_ascii=True) + "\n", json.dumps({"a": json.dumps({"q": comment})}) + "\n",
             f"<td>{html.escape(comment)}</td>\n", f"<p>{html.escape(comment, quote=True).replace(' ', '&nbsp;')}</p>\n"]
    for where in ("docs/case_studies.md", "paper/sections/natural.tex", "results/runs/natural-pr-v1/analysis.md",
                  "experiments/prompts/natural/agent_prompts_natural.jsonl", "src/tracecontract/x.py"):
        for text in forms:
            n, out = _report(text, where, natural)
            assert (n, out) == (1, f"{where}:1: natural short text (NP-95)\n"), (where, text)
    # Below the minimum (3 words with a letter and 12 characters), or not all the words in a row: not matched.
    for text in ("Don't mutate", "mutate defaults", "Swap thumbnails for previews."):
        assert _report(text, "docs/case_studies.md", natural)[0] == 0, text
    assert npv.TextWindows.whole_tokens(npv.normalise("Use a set.")) is None  # 3 words, 10 characters: too generic
    assert npv.TextWindows.whole_tokens(npv.normalise("Looks good")) is None


SHORT_CODE = "Use `os.replace` for the atomic rename."  # NP-97's review comment: 39 characters
SHORT_ACCENT = "Show naïve résumé previews first."  # NP-97's reply, with accented letters


def _np97(tasks_root: Path, events: tuple[str, ...] = (SHORT_CODE, SHORT_ACCENT)) -> None:
    td = tasks_root / "NP-97"
    td.mkdir(exist_ok=True)
    (td / "session.json").write_text(json.dumps({"session_id": "s97", "population": "natural:pr-review", "events": [
        {"event_id": f"s97/{i}", "author": "human", "text": t} for i, t in enumerate(events)]}), encoding="utf-8")


def test_latex_and_decomposed_copies_of_a_short_text(tasks_root):
    r"""The paper is LaTeX: a short comment quoted there with its code in \texttt or \verb, with emphasis, or with accent
    commands (na\"ive, na\"{i}ve, {\"i}, \"\i, r\'esum\'e) is found, also inside a JSON string; so is a copy in
    decomposed form (NFD), as written or JSON-escaped, and a natural text that is itself decomposed, in either form."""
    _np97(tasks_root)
    nm = scan.natural_material(tasks_root)
    nfd = unicodedata.normalize("NFD", SHORT_ACCENT)
    assert nfd != SHORT_ACCENT
    forms = [r"Use \texttt{os.replace} for the atomic rename.", r"Use \verb|os.replace| for the atomic rename.",
             r"Use \verb+os.replace+ for the \emph{atomic} rename.",
             r"\enquote{Use \texttt{os.replace} for the atomic rename.}",
             json.dumps({"tex": r"Use \texttt{os.replace} for the atomic rename."}),
             r"Show na\"ive r\'esum\'e previews first.", r"Show na\"{i}ve r\'{e}sum\'{e} previews first.",
             r"Show na{\"i}ve r{\'e}sum{\'e} previews first.", r"\textit{Show na\"\i ve r\'esum\'e previews first.}",
             nfd, json.dumps({"q": nfd}), json.dumps({"q": nfd}, ensure_ascii=False)]
    for text in forms:
        assert _report(f"{text}\n", "paper/sections/natural.tex", nm) == (
            1, "paper/sections/natural.tex:1: natural short text (NP-97)\n"), text
    for text in (r"Use \texttt{os.rename} for the atomic rename.", r"Show na\"ive r\'esum\'e pictures first."):
        assert _report(text, "paper/sections/natural.tex", nm)[0] == 0, text
    _np97(tasks_root, (nfd,))  # the natural text itself decomposed
    nm = scan.natural_material(tasks_root)
    for text in (SHORT_ACCENT, nfd, r"Show na\"ive r\'esum\'e previews first."):
        assert _report(text, "docs/notes.md", nm) == (1, "docs/notes.md:1: natural short text (NP-97)\n"), text


def test_a_short_part_and_a_short_quote_are_matched_whole(natural):
    """NP-95's issue is long only by its traceback: its own sentence, too short for a window once the frames and the
    traceback's header line are cut out (even without the pre-natural corpus, which holds that line), is matched whole.
    A contract quote shorter than a window of its event is matched as itself."""
    assert npv.thread_segments(NP95_ISSUE) == [f"{OWN_SENTENCE}\n\n"]
    assert _report(f"The issue opens: {OWN_SENTENCE}", "docs/case_studies.md", natural) == (
        1, "docs/case_studies.md:1: natural short text (NP-95)\n")
    assert _report(f"The requirement quotes '{SHORT_QUOTE.upper()}'.", "paper/sections/natural.tex", natural) == (
        1, "paper/sections/natural.tex:1: natural short text (NP-95)\n")
    assert _report("Traceback (most recent call last):\n" + LIB_FRAME, "docs/x.md", natural)[0] == 0


def test_every_task_directory_is_read(tasks_root, natural):
    """A family whose compilation stopped half-way (no task.json, a session without a population) is read like any
    other: its thread text and its check ids are found. A directory with a rejection record only is read and holds
    nothing to find."""
    assert {"NP-92", "NP-93"} <= set(natural.task_ids)
    assert _report(f"> {HALF_BUILT}", "docs/notes.md", natural) == (1, "docs/notes.md:1: natural text window (NP-92)\n")
    assert _report(f"B1 failed on {HALF_BUILT_CHECK}", "docs/notes.md", natural) == (
        1, "docs/notes.md:1: check id of a natural task (NP-92)\n")


def test_a_task_file_that_cannot_be_read_stops_the_scan(tasks_root, screening):
    """The checks fail closed: a session, contract, candidate, verifier record or task record that exists but cannot
    be parsed stops the scan instead of being skipped."""
    texts, _ = screening
    for rel in ("NP-92/session.json", "NP-95/contracts/full_session.json", "NP-92/verifiers/repo_tests/selection.json",
                "NP-95/task.json"):
        f = tasks_root / rel
        good = f.read_bytes()
        f.write_text('{"events": [', encoding="utf-8")
        with pytest.raises(ValueError, match=r"--natural-texts: .*cannot be read as JSON"):
            scan.natural_material(tasks_root)
        with pytest.raises(SystemExit, match="cannot be read as JSON"):
            scan.main("--natural-texts", str(tasks_root), "--screening-texts", str(texts))
        f.write_bytes(good)
    cand = next((tasks_root / "NP-90" / "candidates").glob("*.json"))
    cand.write_bytes(b"\xff\xfe not json")
    with pytest.raises(ValueError, match="cannot be read as JSON"):
        scan.natural_material(tasks_root)


def test_frames_of_the_repositorys_own_installed_package_are_kept(tasks_root, natural):
    own = npv.SnapshotFiles(tasks_root.parent / "snapshots" / "NP-91").holds
    package = OWN_FRAME.index("fx_widgets/")  # kept from its package's path on: the base snapshot holds the file
    assert npv.thread_segments(OWN_FRAME, own) == [OWN_FRAME[package:]]
    assert npv.library_frames(SITE_LIB_FRAME, own) == [(0, len(SITE_LIB_FRAME))]  # a library the snapshot does not hold
    lib = SITE_LIB_FRAME.index("fxthirdparty/")
    assert npv.thread_segments(SITE_LIB_FRAME) == [SITE_LIB_FRAME[lib:]]  # no snapshot to ask: kept
    assert "docs/notes.md:1: natural text window (NP-91)" in _report(OWN_FRAME, "docs/notes.md", natural)[1]
    # A module of the repository's own package that the installed release has and the base snapshot lacks: its
    # package is a directory of the snapshot, so the frame is the repository's own and is kept.
    newer = OWN_FRAME.replace("fx_widgets/gallery.py", "fx_widgets/legacy/zoom.py")
    assert own(newer.split('"')[1]) is True and npv.library_frames(newer, own) == [(0, newer.index("fx_widgets/"))]
    assert own("/opt/venv/lib/python3.12/site-packages/fxthirdparty/loop.py") is False
    # A File line with no source line: the prose after it is no source line, and stays in the texts.
    assert npv.library_frames(BARE_FILE + AFTER_BARE) == [(0, len(BARE_FILE))]
    assert _report(f"Quote: {AFTER_BARE}", "docs/notes.md", natural) == (1, "docs/notes.md:1: natural text window (NP-91)\n")


def test_verbatim_forms_are_read(natural):
    """A copy without spaces between its words (CJK), with tags between the words, with line numbers, inside a JSON
    string inside a JSON string, or percent-encoded."""
    words = COMMENT_TEXT.split()
    tagged = " ".join(f"<em>{' '.join(words[i:i + 3])}</em>" for i in range(0, len(words), 3))
    numbered = "".join(f"{i:6}\t{line}\n" for i, line in enumerate(LIST_TEXT.splitlines(), 1))
    arrows = "".join(f"{i:6}→{line}\n" for i, line in enumerate(LIST_TEXT.splitlines(), 1))
    cases = [
        ("docs/notes.md", f"问题描述：{CJK_TEXT}。", "NP-91"),
        ("results/runs/natural-x/report.html", f"<p>{tagged}</p>", "NP-90"),
        ("experiments/prompts/natural/agent_prompts_natural.jsonl", json.dumps({"prompt": f"Read:\n{numbered}"}), "NP-91"),
        ("experiments/prompts/natural/agent_prompts_natural.jsonl", json.dumps({"prompt": f"Read:\n{arrows}"}), "NP-91"),
        ("data/x.json", json.dumps({"args": json.dumps({"text": LIST_TEXT})}), "NP-91"),
        ("docs/notes.md", f"see https://example.org/search?q={quote(COMMENT_TEXT)}", "NP-90"),
    ]
    for where, text, task in cases:
        n, out = _report(text, where, natural)
        assert n == 1 and out.endswith(f"natural text window ({task})\n"), (where, text[:40])


def test_planted_repository_name_and_owner_are_found_by_location_only(natural, capsys):
    cases = [
        ("results/runs/natural-fx/analysis.md", "intro\nThe fx-widgets project and FXNAT.\n", 2),  # bare names in scope
        ("docs/notes.md", "The fxnat project.\n", 0),  # out of scope, a name that may be an ordinary word
        ("docs/notes.md", "The fx-widgets project.\n", 1),  # a name with a separator is no ordinary word
        ("docs/notes.md", "see https://github.com/fx-org/fx-widgets/pull/3\n", 2),  # owner URL form and the name
        ("docs/notes.md", "fork: git@github.com:someone/fx-widgets.git\n", 1),  # the name after any account
        ("docs/notes.md", "upstream is FX-ORG/fx-widgets\n", 1),  # <owner>/<name>
        ("docs/notes.md", "https://github.com/{owner}/fxnat\n", 1),  # a masked owner: the name only
        ("data/x.json", '"fx-widgetsplus", "my.fx-widgets", "fx-widgets_2", "/fx-orgs/x"\n', 0),  # not the name or owner
        ("data/manifests/third_party_downloads.json", '    "url": "https://github.com/fx-org/fx-widgets",\n', 0),
        ("data/manifests/other.json", '    "url": "https://github.com/fx-org/fx-widgets",\n', 2),
        ("data/manifests/screening_natural_aidev.json", '    "path": "fx-widgets/core.py",\n', 0),
        ("data/manifests/screening_natural_aidev.json", '    "note": "fx-widgets/core.py",\n', 1),
    ]
    for where, text, n in cases:
        assert scan.scan_natural(text, where, where, natural) == n, (where, text)
    out = capsys.readouterr().out
    assert "results/runs/natural-fx/analysis.md:2: natural repository name (NP-90)" in out
    assert "results/runs/natural-fx/analysis.md:2: natural repository name (NP-91)" in out
    assert "docs/notes.md:1: natural repository owner in a URL (NP-91)" in out
    assert all(s not in out.lower() for s in ("fx-widgets", "fx-org", "fxnat"))
    assert scan.scan_natural("natural: fx-org/fx-widgets", "commit abc [message]", None, natural) == 1  # push metadata
    assert scan.scan_natural("natural: fxnat", "commit abc [message]", None, natural) == 0
    capsys.readouterr()


def test_repository_forms_beyond_the_exact_name(natural):
    """The package spelling, a fork without a host, and the owner's own page without a trailing slash."""
    cases = [
        ("results/runs/natural-x/analysis.md", "module fx_widgets.render failed\n", "natural repository name (NP-91)"),
        ("docs/notes.md", "fork: someone/fx-widgets\n", "natural repository name (NP-91)"),
        ("docs/notes.md", "see https://github.com/fx-org for the organisation\n", "natural repository owner in a URL (NP-91)"),
        ("docs/notes.md", "the organisation (github.com/FX-ORG).\n", "natural repository owner in a URL (NP-91)"),
    ]
    for where, text, kind in cases:
        assert _report(text, where, natural) == (1, f"{where}:1: {kind}\n"), text
    # A host that bears the owner's name, and the owner as a word, are no URL of the owner's account.
    for text in ("docs at https://fx-org.example.net/guide\n", "the fx-org team\n", "https://example.org//fx-org.io\n"):
        assert _report(text, "docs/notes.md", natural)[0] == 0, text


def test_a_bare_name_counts_in_the_natural_arms_own_files_only(natural):
    """NP-90's repository name, ``fxnat``, could be an ordinary word: as a bare word it is reported in the natural arm's
    own files (a natural run's outputs, the natural prompts, the natural records, a natural task), not in the
    controlled tasks, the first prompt export, the study's other records or its documents. Its repository forms are
    reported everywhere."""
    line = "The fxnat step comes next.\n"
    for where in ("results/runs/natural-pr-v1/analysis.md", "experiments/prompts/natural/agent_prompts_natural.jsonl",
                  "experiments/natural_workflow/natural_phase.js", "data/manifests/natural_tasks_index.json",
                  "data/manifests/screening_natural_aidev_s9x.json", "tasks/NP-03/session.json", "data/natural/x.json"):
        assert scan.bare_name_scope(where), where
        assert _report(line, where, natural) == (1, f"{where}:1: natural repository name (NP-90)\n"), where
    # The rejection ledger is a natural-arm record too (its S9 and S10 rows), though its name does not say so.
    assert scan.bare_name_scope("data/manifests/rejection_ledger.json")
    assert _report('    "repository": "fxnat",\n', "data/manifests/rejection_ledger.json", natural) == (
        1, "data/manifests/rejection_ledger.json:1: natural repository name (NP-90)\n")
    for where in ("tasks/CS-02/verifiers/initial_plain/tests/test_existing_suite.py", "data/controlled/x.json",
                  "data/manifests/third_party_downloads.json", "data/manifests/provenance_index.json",
                  "experiments/prompts/workflows/tracecontract-research-sweep__wf_0de8dc3d-8f3.js",
                  "experiments/protocol.md", "results/runs/pilot-v0.3.3/report.html", "docs/notes.md",
                  "src/tracecontract/natural_pr.py", "tests/test_scan_natural.py", "paper/sections/natural.tex"):
        assert not scan.bare_name_scope(where), where
        assert _report(line, where, natural)[0] == 0, where
        assert _report("see https://github.com/{owner}/fxnat\n", where, natural)[0] == 1, where
    # A distinctive name (a separator or a digit) is no ordinary word: reported in every file.
    assert _report("the fx-widgets gallery\n", "tasks/CS-02/notes.md", natural)[0] == 1
    assert not hasattr(scan, "NAME_ALLOW")  # no list of reviewed words: the scope rule decides


def test_only_the_authors_published_address_is_allowed():
    """D84: the owner gave the author's Cornell address for publication. That address alone is allowed (in any case);
    another address at the same domain, or one that only starts with it, is still reported."""
    def found(line: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return scan.scan_text(line, "README.md", [])
    assert found("Author: Raj Kashikar, Cornell University (rsk239@cornell.edu)\n") == 0
    assert found("Author: RSK239@Cornell.EDU\n") == 0
    at = "@"  # built at run time, as in the e-mail tests below, so that the scan of this file reports no address
    assert found(f"Contact: fx-person{at}cornell.edu\n") == 1
    assert found(f"Contact: rsk239x{at}cornell.edu\n") == 1
    assert found(f"Contact: rsk239{at}cornell.edu.mail-fixture.io\n") == 1


def test_every_exemption_states_its_reason():
    for path, (key, reason) in scan.NATURAL_RECORDS.items():
        assert path.startswith("data/") and re.fullmatch(r"[a-z_]+", key) and isinstance(reason, str) and len(reason) > 40
    for table in (scan.HANDLE_ALLOW, scan.ALLOW):
        assert table and all(isinstance(r, str) and len(r) > 15 for r in table.values())


def test_code_lines_and_check_ids_of_the_natural_tasks(natural):
    """B1's check ids are reported in every file; a line of a natural task's patches or verifier files everywhere but
    the study's own code and the controlled tasks (study_code): its code directories, the paper's scripts and the
    unfinished packages kept as patches."""
    for where in ("docs/notes.md", "results/runs/natural-pr-v1/analysis.md", "experiments/prompts/natural/x.jsonl",
                  "paper/sections/natural.tex", "src/tracecontract/x.py", "paper/make_tables.py", "docs/wip/x.patch"):
        assert _report(f"| {B1_CHECKS[1]} | failed |\n", where, natural) == (
            1, f"{where}:1: check id of a natural task (NP-90)\n"), where
    assert _report("see test_mod.py::test_missing_values", "docs/notes.md", natural)[0] == 1  # without its directories
    for where in ("docs/notes.md", "results/runs/natural-pr-v1/analysis.md", "experiments/prompts/natural/x.jsonl",
                  "paper/sections/natural.tex", "docs/wip/README.md", "tasks/NP-03/notes.md"):
        assert not scan.study_code(where), where
        n, out = _report(f"The test asserts:\n    {UPSTREAM_LINE}\n", where, natural)
        assert (n, out) == (1, f"{where}:2: code line of a natural task (NP-90)\n"), where
    for where in ("src/tracecontract/x.py", "tests/test_x.py", "scripts/x.py", "tasks/CS-01/x.json", "data/controlled/x",
                  "paper/make_tables.py", "docs/wip/natural-analysis-wp-g.patch"):
        assert scan.study_code(where), where
        assert _report(UPSTREAM_LINE, where, natural)[0] == 0, where
    assert _report(json.dumps({"prompt": f"Patch:\n+    {UPSTREAM_LINE}\n"}), "experiments/p.jsonl", natural)[0] == 1
    assert _report("x" + UPSTREAM_LINE + "x", "docs/notes.md", natural)[0] == 0  # not a line of its own
    assert _report("tests/test_mod.py::test_missing_values_2", "docs/notes.md", natural)[0] == 0  # another test


BASE_ONLY = "    return fx_render_gallery(widget_cache, zoom_level=zoom)"  # a line of NP-90's base snapshot only
BASE_AND_B1 = "from fxnat.mod import add"  # a line of NP-90's base snapshot and of B1's overlay


def _base_file(tasks_root: Path, name: str = "render.py", text: str = f"def render(widget_cache, zoom):\n{BASE_ONLY}\n"):
    (tasks_root.parent / "snapshots" / "NP-90" / "fxnat" / name).write_text(text, encoding="utf-8")


def test_base_snapshot_code_is_found_outside_the_publisher(tasks_root):
    """A line of a natural task's base snapshot (the upstream repository at its base commit) is reported by the scan,
    and so by the export guard, in every file but the study's own code, also JSON-escaped; a line that B1's overlay
    holds as well is reported once, as the task's code line."""
    _base_file(tasks_root)
    nm = scan.natural_material(tasks_root)
    assert nm.base_snapshot("NP-90")[1] > 0 and nm.base_snapshot("NP-92") is None and "NP-90" in nm.base_code.labels
    for where in ("docs/notes.md", "paper/sections/natural.tex", "results/runs/natural-pr-v1/analysis.md",
                  "experiments/prompts/natural/agent_prompts_natural.jsonl", "README.md"):
        for text in (f"The base reads:\n{BASE_ONLY}\n", json.dumps({"prompt": f"Context:\n{BASE_ONLY}\nGo on."}) + "\n"):
            line = text.count("\n", 0, text.index("fx_render_gallery")) + 1
            assert _report(text, where, nm) == (
                1, f"{where}:{line}: code line of a natural task's base snapshot (NP-90)\n"), (where, text)
    for where in ("src/tracecontract/x.py", "tests/test_x.py", "scripts/x.py", "tasks/CS-01/x.json", "data/controlled/x",
                  "paper/make_tables.py"):
        assert _report(BASE_ONLY, where, nm)[0] == 0, where
    assert _report(f"{BASE_AND_B1}\n", "docs/notes.md", nm) == (1, "docs/notes.md:1: code line of a natural task (NP-90)\n")
    assert "code line(s) of 2 base snapshot(s)" in scan.natural_summary(nm)  # NP-90's and NP-91's
    # Not in the controlled arm's outputs, which show the controlled tasks' code and the study's tools at work; a
    # natural run's outputs are no such output, and the patches' and verifiers' lines are reported there as before.
    for where in ("results/runs/pilot-v0.3.3/report.html", "results/runs/fresh-v1/results.jsonl",
                  "data/fresh/fresh-v1/audit_CS-03.json", "results/harbor_validation/x/probe/result.json"):
        assert not scan.base_code_scope(where) and _report(BASE_ONLY, where, nm)[0] == 0, where
        assert _report(UPSTREAM_LINE, where, nm)[0] == 1, where
    assert scan.base_code_scope("results/runs/natural-pr-v1/analysis.md") and scan.base_code_scope(None)


def test_a_base_line_of_common_words_tells_no_repository_apart(tasks_root):
    """A base snapshot holds a whole repository, with idioms that the study's own files share (an except clause): its
    line is used only if a word of it is in at most one line of the corpus written before any natural task. A line of a
    task's patches or verifiers is not filtered so. A record field that names the repository by design (the licence
    record's URL) is no code of it."""
    corpus = ["except (KeyError, ValueError):", "    except (KeyError, ValueError) as error:"]
    generic = npv.generic_lines(["\n".join(corpus)])
    counts = npv._line_counts(generic)
    assert not npv.distinctive_line("except (ValueError, KeyError):", counts)
    assert npv.distinctive_line("except (ValueError, FxGalleryError):", counts)
    url = '    "https://example.org/fxgallerydocs/stable/index.html",'
    _base_file(tasks_root, "errors.py", f"try:\n    pass\nexcept (ValueError, KeyError):\n    pass\n"
                                        f"except (ValueError, FxGalleryError):\n    pass\nDOCS = [\n{url}\n]\n")
    (tasks_root / "NP-90" / "verifiers" / "repo_tests" / "test_errors.txt").write_text("except (ValueError, KeyError):\n")
    nm = npv.NaturalMaterial.load(tasks_root, generic=generic)
    assert _report("except (ValueError, FxGalleryError):\n", "docs/notes.md", nm) == (
        1, "docs/notes.md:1: code line of a natural task's base snapshot (NP-90)\n")
    assert _report("except (ValueError, KeyError):\n", "docs/notes.md", nm) == (
        1, "docs/notes.md:1: code line of a natural task (NP-90)\n")  # the verifier's line, not the base's
    record = f'    "url": {url.strip()}\n'
    assert _report(record, "data/manifests/third_party_downloads.json", nm)[0] == 0
    assert _report(record, "data/manifests/other.json", nm) == (
        1, "data/manifests/other.json:1: code line of a natural task's base snapshot (NP-90)\n")


def test_a_recorded_base_snapshot_must_be_read(tasks_root, monkeypatch):
    """The base-snapshot check fails closed: a snapshot that a task's snapshot.json records but that is missing or
    yields no code line, or a file of it that cannot be read, stops the scan. A task that records none (NP-92, NP-95)
    needs none."""
    snap = tasks_root.parent / "snapshots" / "NP-90"
    kept = tasks_root.parent / "kept-snapshot"
    shutil.copytree(snap, kept)
    read_bytes = Path.read_bytes

    def unreadable(self: Path) -> bytes:
        if self.name == "mod.py" and "snapshots" in self.parts:
            raise PermissionError(13, "Permission denied")
        return read_bytes(self)

    with monkeypatch.context() as m:
        m.setattr(Path, "read_bytes", unreadable)
        with pytest.raises(ValueError, match=r"--natural-texts: .*mod\.py: cannot be read \(Permission denied\)"):
            scan.natural_material(tasks_root)
    for f in snap.rglob("*.py"):
        f.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="NP-90: no code line could be read from its base snapshot"):
        scan.natural_material(tasks_root)
    shutil.rmtree(snap)
    with pytest.raises(ValueError, match="NP-90: no base snapshot at .*, though its snapshot.json records one"):
        scan.natural_material(tasks_root)
    shutil.copytree(kept, snap)
    assert scan.natural_material(tasks_root).base_snapshot("NP-90")[1] > 0


def test_large_python_files_are_read_and_binary_files_counted(tasks_root):
    """A base snapshot's Python file over 1 MB (a generated table, vendored code) is read like any other, and so is a
    verifier's text file of that size; a file with a NUL byte holds no line of code, and the summary counts it."""
    filler = "".join(f"TABLE_{i:06d} = compute_entry({i}, scale=FACTOR)\n" for i in range(24000))
    assert len(filler) > 1_000_000
    tail = "    return fx_large_lookup(table_cache, entry_index=key)"
    _base_file(tasks_root, "tables.py", filler + tail + "\n")
    overlay = tasks_root / "NP-90" / "verifiers" / "repo_tests"
    big = "    assert fx_large_verifier(table_cache, entry_index=key)"
    (overlay / "test_tables.txt").write_text(filler + big + "\n", encoding="utf-8")
    (overlay / "fixture.bin").write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR")
    nm = scan.natural_material(tasks_root)
    assert _report(tail, "docs/notes.md", nm) == (1, "docs/notes.md:1: code line of a natural task's base snapshot (NP-90)\n")
    assert _report(big, "docs/notes.md", nm) == (1, "docs/notes.md:1: code line of a natural task (NP-90)\n")
    assert [p.name for p in nm.binary] == ["fixture.bin"]
    assert "(1 binary file(s) not read as code)" in scan.natural_summary(nm)


def test_common_idioms_are_no_code_line():
    """A line in the generic set (the corpus written before any natural task) is not looked for."""
    needles = [("NP-90", "from pathlib import Path"), ("NP-90", UPSTREAM_LINE)]
    code = npv.CodeLines(needles, generic=npv.generic_lines(["import os\nfrom pathlib import Path\n"]))
    assert code.n_needles == 1 and code.labels == frozenset({"NP-90"})
    assert code.find("from pathlib import Path\n") == [] and len(code.find(UPSTREAM_LINE)) == 1
    # A line of short words only is too generic to tell apart (MIN_CODE_WORD), whatever its length.
    assert npv.code_line("dx, dy = x1 - x0, y1 - y0 + z9") is None and npv.code_line(UPSTREAM_LINE) == UPSTREAM_LINE
    lines = scan.pre_natural_lines()
    if lines is None:
        pytest.skip("the frozen pre-natural revision is not in this clone")
    assert "from pathlib import Path" in lines and "import subprocess" in lines and UPSTREAM_LINE not in lines


def test_code_line_search_is_exact():
    """CodeLines finds a line exactly where a naive search over every offset does: the line as a substring of the
    whitespace-collapsed text, with no word character joined to either end, whichever of its words indexes it."""
    vocab = ["self", "value", "return", "x", "_cache", "fx_widgets", "None", "42", "if", "ab"]
    seps = [" ", "(", ")", ".", " = ", ", ", "  ", "\n    ", "_", ""]
    rng = random.Random(11)

    def code(n: int) -> str:
        return "".join(rng.choice(vocab) + rng.choice(seps) for _ in range(n))

    for _ in range(150):
        needles = [(f"L{i}", " ".join(code(rng.randint(2, 6)).split())) for i in range(4)]
        generic = npv.generic_lines([code(rng.randint(2, 8)) for _ in range(5)])
        searched = code(rng.randint(0, 30))
        if rng.random() < 0.7:
            label, line = rng.choice(needles)
            cut = rng.randint(0, len(searched))
            searched = searched[:cut] + rng.choice(["", " ", "x"]) + line + rng.choice(["", " ", "x", "\n"]) + searched[cut:]
        cl = npv.CodeLines(needles, generic=generic)
        got = {label for _, label in cl.find(searched)}
        flat = re.sub(r"\s+", " ", searched)
        expected = set()
        for label, line in needles:
            n = " ".join(line.split())
            if not n or n in generic or not re.search(r"\w", n) or any(_occurs(n, g) for g in generic):
                continue
            if _occurs(n, flat):
                expected.add(label)
        assert got == expected, (needles, searched)


def _occurs(n: str, text: str) -> bool:
    """Whether ``n`` is a substring of ``text`` with no word character joined to either end (naively, at every offset)."""
    return any(text.startswith(n, i) and not (i > 0 and re.match(r"\w", n[0]) and re.match(r"\w", text[i - 1])) and not (
        i + len(n) < len(text) and re.match(r"\w", n[-1]) and re.match(r"\w", text[i + len(n)]))
        for i in range(len(text) - len(n) + 1))


def test_a_line_the_corpus_holds_within_a_line_is_no_code_line():
    """A natural line that a line of the pre-natural corpus holds within it (the head of a call that the corpus line
    completes) is left out, as a whole corpus line is: the corpus was written before any natural task existed. A line
    that adds a word of its own, or that the corpus holds only joined to a word character, is still looked for."""
    generic = npv.generic_lines(["    r = run_python(_snippet(cases), timeout=60.0)\n    assert r.ok_flag\n"])
    head = "r = run_python(_snippet("
    own = "r = run_python(_snippet(fx_widget_spec), timeout=TIMEOUT)"
    joined = "un_python(_snippet(cases"  # in the corpus line only inside the words "run_python" and "cases)"
    code = npv.CodeLines([("NP-90", head), ("NP-90", own), ("NP-91", joined)], generic=generic)
    assert code.n_needles == 2 and code.labels == frozenset({"NP-90", "NP-91"})
    assert code.find("x = 1\nr = run_python(_snippet(\n    other))\n") == []
    assert [label for _, label in code.find(f"y\n{own}\n")] == ["NP-90"]
    assert code.find("q = run_python(_snippet(cases_two)") == []  # joined to "r" here too
    assert [label for _, label in code.find("q = un_python(_snippet(cases)\n")] == ["NP-91"]
    assert npv._held_within({head, own, joined, "never_in_the_corpus("}, generic) == {head}
    assert npv._held_within({head}, frozenset()) == set()


def test_a_screened_text_the_corpus_holds_within_a_line_is_not_looked_for():
    """The idiom rule of code lines (decision log D72) for the screened comments' texts (D78, D81): under an idiom
    label, a text with no window of words that a line of the pre-natural corpus holds, as the line or within it,
    whitespace collapsed and case kept, also without a leading diff marker, is not looked for, neither whole nor by its
    character windows. A text with a word of its own, one that the corpus holds only joined to a word character, one
    with a copy under its label that is no idiom, one with a window of words, and every text under another label (a
    natural task's) are looked for as without the corpus."""
    call = "frobnicate_widget_totals(alpha_value, beta_value, gamma_value, delta_value, epsilon_value)"
    kwargs = "alpha=1, beta=2, gamma=3, delta=4, epsilon=5, zeta=6, eta=7, theta=8"
    corpus = f"from abc import ABC, abstractmethod\n    total = {call} + 1\n    configure({kwargs})\n"
    generic = npv.generic_lines([corpus])
    texts = [("S1", "from abc import ABC"),  # held within a corpus line: an idiom
             ("S2", "from abc import ABCMeta"),  # a word of its own
             ("S3", "from abc import AB"),  # in the corpus line only joined to "C"
             ("S4", call),  # character windows but no window of words, and held within a corpus line: an idiom
             ("S5", "FROM ABC IMPORT ABC"), ("S5", "from abc import ABC"),  # the first copy is no idiom (case counts)
             ("S6", "Please keep the old default for the cache size here."),
             ("S7", "import ABC"),  # held within too, but below the minimum: nothing to look for, so not counted
             ("S8", "+from abc import ABC"),  # a diff hunk's added line: an idiom without its marker
             ("S9", "from abc\nimport ABC"),  # two lines that one corpus line holds, whitespace collapsed: an idiom
             ("S10", kwargs),  # held within a corpus line, but with a window of words: looked for
             ("NP-90", "from abc import ABC")]  # a natural task's own text: looked for
    labels = {f"S{i}" for i in range(1, 11)}
    tw, plain = npv.TextWindows(texts, generic=generic, idiom_labels=labels), npv.TextWindows(texts)
    assert (tw.n_idioms, plain.n_idioms) == (4, 0)  # S1, S4, S8 and S9

    def found(t: npv.TextWindows, text: str) -> set[str]:
        return {label for _, _, label in t.find(text)}

    corpus_line = "from abc import ABC, abstractmethod\n"
    assert found(plain, corpus_line) == {"S1", "S5", "S8", "S9", "NP-90"} and found(tw, corpus_line) == {"S5", "NP-90"}
    assert found(plain, f"y = {call}\n") == {"S4"} and found(tw, f"y = {call}\n") == set()
    assert found(tw, f"configure({kwargs})\n") == found(plain, f"configure({kwargs})\n") == {"S10"}
    assert found(tw, "from abc import ABCMeta\n") == {"S2"} and found(tw, "from abc import AB\n") == {"S3"}
    assert found(tw, "Note: please keep the old default for the cache size here.") == {"S6"}
    # Without idiom labels, or with a corpus that holds none of the texts, nothing is left out.
    assert npv.TextWindows(texts, generic=generic).n_idioms == 0
    assert npv.TextWindows(texts, generic=npv.generic_lines(["import os\n"]), idiom_labels=labels).n_idioms == 0


def test_only_screened_idioms_with_no_window_of_words_are_left_out():
    """With a corpus, the matcher finds what it finds without one, less the texts under an idiom label that have no
    window of words and that a corpus line holds, as the line or within it (whitespace collapsed, case kept, also
    without a leading diff marker): a naive check over random texts and corpora."""
    vocab = ["from", "abc", "import", "ABC", "x_1", "Path", "os", "alpha", "beta", "gamma", "42", "a"]
    rng = random.Random(23)

    def words(n: int) -> str:
        return " ".join(rng.choice(vocab) for _ in range(n))

    def forms(text: str) -> list[str]:
        c = " ".join(text.split())
        rest = c[1:].lstrip() if c[:1] in ("+", "-") else ""
        return [x for x in (c, rest) if x]

    for _ in range(200):
        lines = [words(rng.randint(2, 9)) for _ in range(4)]
        generic = npv.generic_lines(["\n".join(lines) + "\n"])
        texts = []
        for i in range(6):
            if rng.random() < 0.5:
                toks = rng.choice(lines).split()
                a = rng.randint(0, len(toks) - 1)
                text = " ".join(toks[a:rng.randint(a + 1, len(toks))])
                if rng.random() < 0.3:
                    text = rng.choice("+-") + text
                if rng.random() < 0.3:
                    text = text.replace(" ", "\n", 1)
            else:
                text = words(rng.randint(1, 10))
            texts.append((f"S{i}", text))
        labels = {f"S{i}" for i in range(6) if rng.random() < 0.6}
        tw, plain = npv.TextWindows(texts, generic=generic, idiom_labels=labels), npv.TextWindows(texts)
        searched = "\n".join(rng.sample(lines, 2)) + " " + words(rng.randint(0, 12))
        left_out = {label for label, text in texts if label in labels
                    and npv.TextWindows([(label, text)]).n_word_windows == 0
                    and any(_occurs(f, g) for f in forms(text) for g in generic)}
        expected = {label for _, _, label in plain.find(searched)} - left_out
        assert {label for _, _, label in tw.find(searched)} == expected, (lines, texts, labels, searched)


def test_a_screened_import_line_left_alone_by_the_cuts_is_an_idiom(tasks_root, tmp_path):
    """D78's finding: a screened issue's import line, left on its own between lines that the corpus holds (and that are
    cut), was matched whole in the study's own files, which hold a longer line that holds it within it. It is an idiom
    now (D81). The comment's own text is still found; so is the same line in a natural task's own text, which the
    pre-push gate looks for as before; and the scan's last line counts the text left out."""
    rows = [{"comment_id": 601, "comment_body": "Please register the widget plugins before the loader starts up.",
             "issue_title": "", "issue_body": "import os\nfrom abc import ABC\nimport sys\n", "pr_title": "",
             "diff_hunk": ""}]
    texts = tmp_path / "outside" / "s9_idiom.jsonl"
    texts.parent.mkdir(exist_ok=True)
    texts.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    cuts = "import os\nimport sys\n"
    with_line = npv.generic_lines([cuts + "from abc import ABC, abstractmethod\n"])
    before = npv.NaturalMaterial.load(tasks_root, screening=[texts], generic=npv.generic_lines([cuts]))
    nm = npv.NaturalMaterial.load(tasks_root, screening=[texts], generic=with_line)
    where = "src/tracecontract/x.py"
    line = "from abc import ABC, abstractmethod\n"
    assert _report(line, where, before) == (1, f"{where}:1: natural short text (screened comment 601)\n")
    assert _report(line, where, nm) == (0, "")
    comment = "# Please register the widget plugins before the loader starts up.\n"
    assert _report(comment, where, nm) == (1, f"{where}:1: natural text window (screened comment 601)\n")
    assert (before.windows.n_idioms, nm.windows.n_idioms) == (0, 1)
    assert (f"short text(s) matched whole, 1 screened short text(s) left out as idioms of the repository at "
            f"{scan.PRE_NATURAL_REV}), ") in scan.natural_summary(nm)
    assert "left out as idioms" not in scan.natural_summary(before)
    # A natural task whose own text holds the same lines: the gate's texts are all looked for.
    td = tasks_root / "NP-98"
    td.mkdir()
    (td / "session.json").write_text(json.dumps({"session_id": "s98", "population": "natural:pr-review", "events": [
        {"event_id": "s98/0", "author": "human", "text": "import os\nfrom abc import ABC\nimport sys\n"}]}),
        encoding="utf-8")
    gate = npv.NaturalMaterial.load(tasks_root, screening=[texts], generic=with_line)
    assert _report(line, where, gate) == (1, f"{where}:1: natural short text (NP-98)\n")
    assert gate.windows.n_idioms == 1


def test_handle_exemptions_apply_only_where_natural_texts_adds_the_scope(natural, capsys):
    """The CSS at-rules and template references count as code in results/ and experiments/ only: --natural-texts leaves
    the @handle check of tasks/ and data/ as it was."""
    cases = [("data/manifests/x.json", b"reviewed-by=@jdoe-real, assignee=@jdoe-real\n", 2),
             ("tasks/NP-77-notes/review.md", b"approved_by=@jdoe-real\n", 1),
             ("data/x/page.html", b"@page { margin: 0 }\n@scope (.card) { }\n", 2)]
    for where, data, n in cases:
        assert scan.scan_file(where, data, [], [], aidev=True) == n, where
        assert scan.scan_file(where, data, [], [], natural, aidev=True) == n, where
    assert scan.scan_file("experiments/prompts/natural/t.txt", b"INPUTS=@contract\n", [], [], natural) == 0
    assert scan.scan_file("results/runs/x/r.html", b"@page { margin: 0 }\n", [], [], natural) == 0
    # The natural prompts' own words for what they forbid, there only.
    rule = b"// no logins, @handles or e-mail addresses; never @mention anyone\n"
    assert scan.scan_file("experiments/prompts/natural/workflows/w.js", rule, [], [], natural) == 0
    assert scan.scan_file("experiments/prompts/workflows/w.js", rule, [], [], natural) == 2
    assert "jdoe" not in capsys.readouterr().out


def test_emails_handles_and_scopes_under_natural_texts(natural, capsys):
    # Built at run time so that this file holds no address the scan would report (a domain that is not reserved).
    addr = "fx-person" + "@" + "mail-fixture.io"
    assert scan.scan_text(f"from {addr}", "f.md", [], hash_emails=True) == 1
    out = capsys.readouterr().out
    assert out == f"f.md:1: e-mail address (sha256 {scan.email_hash(addr)})\n" and addr not in out
    assert scan.scan_text(f"from {addr}", "f.md", []) == 1 and addr in capsys.readouterr().out  # as before without it
    assert scan.handle_scope("results/runs/x/analysis.md") == (False, frozenset())
    assert scan.handle_scope("results/runs/x/analysis.md", natural=True) == (True, frozenset())
    assert scan.handle_scope("experiments/prompts/natural/x.txt", natural=True)[0]
    assert scan.handle_scope("tasks/CS-01/x.json") == scan.handle_scope("tasks/CS-01/x.json", natural=True)
    css = "@media (prefers-color-scheme: dark) { :root { } }\n@font-face { }"
    assert scan.scan_text(css, "results/r.html", [], handles=True, css=True) == 0
    assert scan.scan_text(css, "results/r.html", [], handles=True) == 2
    assert scan.scan_text("cc @media-person", "results/r.html", [], handles=True, css=True) == 1
    ref = "variant a: INPUTS=@contract MAP_TEXT=@contract STYLE=@1"
    assert scan.scan_text(ref, "experiments/t.txt", [], handles=True, assignments=True) == 0
    assert scan.scan_text(ref, "experiments/t.txt", [], handles=True) == 3
    assert scan.scan_text("thanks = @fx-someone", "experiments/t.txt", [], handles=True, assignments=True) == 1
    # scan_file: with --natural-texts the handle check covers results/ and experiments/ even without --aidev-logins.
    data = b"thanks @fx-someone\n"
    assert scan.scan_file("results/runs/x/analysis.md", data, [], []) == 0
    assert scan.scan_file("results/runs/x/analysis.md", data, [], [], natural) == 1
    out = capsys.readouterr().out
    assert "results/runs/x/analysis.md:1: @handle" in out and "fx-someone" not in out


def test_scan_file_without_natural_texts_is_unchanged(capsys):
    """The file scan of main without --natural-texts: the generic rules, then @handles in tasks/ and data/ only."""
    addr = "fx-person" + "@" + "mail-fixture.io"  # built at run time, as above
    text = f"mail {addr}\n@media x\ncc @fx-someone\nINPUTS=@contract\n".encode()
    assert scan.scan_file("results/runs/x/r.html", text, [], [], aidev=True) == 1
    assert scan.scan_file("data/x/r.html", text, [], [], aidev=True) == 4
    out = capsys.readouterr().out
    assert f"results/runs/x/r.html:1: e-mail address {addr}" in out and "natural" not in out


# --------------------------------------------------------------------------- the screening texts and the AIDev logins

SCREENED = ("The retry loop in the uploader swallows the timeout error, so the job reports success while nothing was "
            "stored; please surface the error to the caller instead.")
SCREENED_SHORT = "Please drop the second retry."
SCREENED_ISSUE_BODY = ("Uploads hang forever on a slow network.\n\n"
                       "=========================== short test summary info ============================\n"
                       "ERROR: Could not find a version that satisfies the requirement fxupload==9.9 (from versions: none)\n")
IMPORT_HUNK = "@@ -1,5 +1,6 @@\n import json\n import subprocess\n+import sys\n import tempfile\n from pathlib import Path\n"


@pytest.fixture
def screening(tmp_path: Path) -> tuple[Path, list[Path]]:
    """A screening text file (``screen_aidev.py --texts-out``) of two sampled comments, neither built, and the two
    screening manifests that sample them."""
    rows = [{"comment_id": 501, "comment_body": SCREENED, "issue_title": "Uploads hang", "issue_body": SCREENED_ISSUE_BODY,
             "pr_title": "Retry uploads on timeout", "diff_hunk": IMPORT_HUNK},
            {"comment_id": 502, "comment_body": SCREENED_SHORT, "issue_title": "", "issue_body": "", "pr_title": "x",
             "diff_hunk": "@@ -1 +1 @@\n-a\n+b\n"}]
    texts = tmp_path / "outside" / "s9_texts.jsonl"
    texts.parent.mkdir()
    texts.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    m9, m9x = tmp_path / "outside" / "s9.json", tmp_path / "outside" / "s9x.json"
    m9.write_text(json.dumps({"sample": {"rows": [{"comment_id": 501}]}}))
    m9x.write_text(json.dumps({"sample": {"id": "S9x"}, "rows": [{"comment_id": 502}]}))
    return texts, [m9, m9x]


def test_screening_texts_cover_every_sampled_comment(tasks_root, screening):
    texts, manifests = screening
    nm = scan.natural_material(tasks_root, [texts], manifests=manifests)
    assert nm.screened == frozenset({501, 502}) and nm.task_ids == ("NP-90", "NP-91", "NP-92", "NP-93", "NP-95")
    where = "experiments/prompts/natural/agent_prompts_natural.jsonl"
    n, out = _report(json.dumps({"prompt": f"Judge this comment:\n{SCREENED}\n"}), where, nm)
    assert (n, out) == (1, f"{where}:1: natural text window (screened comment 501)\n")
    assert _report(f"The reviewer: {SCREENED_SHORT}", where, nm) == (1, f"{where}:1: natural short text (screened comment 502)\n")
    # Cut out of the texts: pytest's banner, pip's resolver error and (with the pre-natural corpus) an import block.
    for text in ("=========================== short test summary info ============================",
                 "ERROR: Could not find a version that satisfies the requirement fxupload==9.9 (from versions: none)"):
        assert _report(text, "docs/notes.md", nm)[0] == 0, text
    if scan.pre_natural_lines() is not None:
        block = "import json\nimport subprocess\nimport sys\nimport tempfile\nfrom pathlib import Path\n"
        assert _report(block, "results/runs/natural-x/report.html", nm)[0] == 0
    # Every sampled comment of both manifests must be in the texts.
    manifests[1].write_text(json.dumps({"rows": [{"comment_id": 502}, {"comment_id": 503}]}))
    with pytest.raises(ValueError, match="lack 1 sampled comment"):
        scan.natural_material(tasks_root, [texts], manifests=manifests)


def test_screening_texts_on_the_command_line(tasks_root, screening, tmp_path):
    texts, manifests = screening
    with pytest.raises(SystemExit, match="needs --natural-texts"):
        scan.main("--screening-texts", str(texts))
    # Without the screening texts, the sampled comments that no task holds go unchecked, and the scan's last line says so.
    assert "no screening texts given: the sampled comments that no natural task holds were not checked" in (
        scan.natural_summary(scan.natural_material(tasks_root)))
    assert "were not checked" not in scan.natural_summary(scan.natural_material(tasks_root, [texts], manifests=manifests))
    with pytest.raises(SystemExit, match="--screening-texts"):  # the real manifests sample comments these texts lack
        scan.main("--natural-texts", str(tasks_root), "--screening-texts", str(texts))
    bad = tmp_path / "outside" / "bad.jsonl"
    bad.write_text('{"no_comment_id": 1}\n')
    with pytest.raises(ValueError, match="no comment_id"):
        list(npv.screening_texts(bad))


def test_aidev_logins_are_those_of_the_first_sample_only(tmp_path):
    """--aidev-logins loads the logins connected to the PRs of the first S9 sample only, as before the natural package:
    the extension's (S9x, protocol §19.2) are not loaded until the extension's S10 is redone (decision log D66, D84). Every
    account of the first sample's PRs is kept, an owner that acts as an account included: no list leaves one out. The
    screening texts, by contrast, must cover the comments of both samples."""
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    pytest.importorskip("duckdb")
    first = json.loads(scan.AIDEV_MANIFEST.read_text(encoding="utf-8"))["sample"]["rows"][0]["comment_id"]
    second = json.loads(scan.SCREENING_MANIFESTS[1].read_text(encoding="utf-8"))["rows"][0]["comment_id"]
    api = "https://api.github.com/repos/"
    tables = {
        "pull_request": [{"id": 1, "number": 1, "user": "Copilot", "repo_url": f"{api}fx-hub-org/r1"},
                         {"id": 2, "number": 2, "user": "Copilot", "repo_url": f"{api}fx-o2/r2"},
                         {"id": 3, "number": 3, "user": "fx-hub-org", "repo_url": f"{api}fx-o3/r3"}],
        "pr_review_comments": [{"id": first, "user": "fx-rev-s9", "user_type": "User",
                                "pull_request_url": f"{api}fx-hub-org/r1/pulls/1"},
                               {"id": second, "user": "fx-rev-s9x", "user_type": "User",
                                "pull_request_url": f"{api}fx-o2/r2/pulls/2"}],
        "pr_commits": [{"pr_id": 2, "author": "fx-committer-s9x", "committer": "web-flow"}],
        "related_issue": [{"pr_id": 2, "issue_id": 300}],
        "issue": [{"id": 300, "user": "fx-issue-s9x"}],
    }
    data = tmp_path / "aidev"
    data.mkdir()
    for name, rows in tables.items():
        cols = list(rows[0])
        types = [pa.int64() if isinstance(rows[0][c], int) else pa.string() for c in cols]
        schema = pa.schema(list(zip(cols, types, strict=True)))
        pq.write_table(pa.table({c: [r[c] for r in rows] for c in cols}, schema=schema), data / f"{name}.parquet")
    # The owner fx-hub-org of the first sample's PR acts as an account (it authors PR 3), so it is a login too.
    assert scan.aidev_logins(data) == ["fx-hub-org", "fx-rev-s9"]
    assert not hasattr(scan, "NOT_PEOPLE")
    ids = scan.sampled_comment_ids()
    assert len(ids) == len(set(ids)) == 684 and first in ids and second in ids


# --------------------------------------------------------------------------- the matchers

def test_window_search_is_exact():
    """The seed-and-extend search finds a window exactly when a naive search over every offset does. The naive search
    is independent of the implementation: its own normalisation, its own reading of JSON escapes, and the window rules
    written out (4 words with a letter, two whitespace-separated tokens), with words of digits and underscores."""
    vocab = ["alpha", "beta", "gamma", "delta", "zeta", "theta", "kappa", "lambda", "sigma", "omega", "42", "2026", "_x",
             "x_1", "7b"]
    rng = random.Random(20261121)

    def text(n: int) -> str:
        return "".join(rng.choice(vocab) + rng.choice([" ", ", ", ".\n", "  ", "-"]) for _ in range(n))

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).lower()

    def windows(src: str) -> tuple[set[str], set[tuple[str, ...]]]:
        s = norm(src)
        words = [(m.start(), m.group()) for m in re.finditer(r"\w+", s)]
        cw = {s[q:q + 60] for q in range(len(s) - 59)
              if " " in s[q + 1:q + 59] and sum(1 for a, w in words if q <= a < q + 60 and lettered(w)) >= 4}
        toks = [w for _, w in words]
        ws = [s[:a].count(" ") for a, _ in words]
        ww = {tuple(toks[t:t + 8]) for t in range(len(toks) - 7)
              if ws[t] != ws[t + 7] and sum(map(lettered, toks[t:t + 8])) >= 4}
        return cw, ww

    def naive(sources, searched) -> set[tuple[str, str]]:
        found = set()
        reads = [searched] + ([searched.encode().decode("unicode_escape")] if "\\" in searched else [])
        for label, src in sources:
            cw, ww = windows(src)
            for r in reads:
                f = norm(r)
                if any(f[i:i + 60] in cw for i in range(len(f) - 59)):
                    found.add((label, "characters"))
                ft = re.findall(r"\w+", f)
                if any(tuple(ft[i:i + 8]) in ww for i in range(len(ft) - 7)):
                    found.add((label, "words"))
        return found

    for _ in range(120):
        sources = [(f"T{i}", text(rng.randint(4, 30))) for i in range(3)]
        searched = text(rng.randint(0, 25))
        if rng.random() < 0.7:
            src = rng.choice(sources)[1]
            a = rng.randint(0, len(src))
            piece = src[a:rng.randint(a, len(src))]
            if rng.random() < 0.3:
                piece = json.dumps(piece)[1:-1]
            cut = rng.randint(0, len(searched))
            searched = searched[:cut] + piece + searched[cut:]
        got = {(label, kind) for _, kind, label in npv.TextWindows(sources).find(searched) if kind != "whole"}
        assert got == naive(sources, searched), (sources, searched)
    # Two texts that share a long run with the searched text: each is found, the second inside the first's run.
    shared = " ".join(rng.choice(vocab[:10]) for _ in range(30))
    sources = [("A", "x_1 x_1 x_1 " + shared), ("B", shared + " kappa")]
    assert {label for _, _, label in npv.TextWindows(sources).find("x_1 x_1 x_1 " + shared + " kappa")} == {"A", "B"}


def test_whole_text_search_is_exact():
    """A short text is found whole exactly when all its words are in a row in the searched text and it reaches the
    minimum (3 words with a letter, 12 characters), by a naive search."""
    vocab = ["alpha", "beta", "gamma", "delta", "zeta", "42", "x_1", "a", "io"]
    rng = random.Random(4)
    for _ in range(300):
        shorts = [(f"S{i}", " ".join(rng.choice(vocab) for _ in range(rng.randint(2, 6)))) for i in range(3)]
        searched = " ".join(rng.choice(vocab) for _ in range(rng.randint(0, 14)))
        if rng.random() < 0.5:
            words = rng.choice(shorts)[1].split()
            sep = rng.choice([" ", ", ", "\n", " (", "**", "&nbsp;"])
            searched += " " + sep.join(w.upper() if rng.random() < 0.3 else w for w in words)
        tw = npv.TextWindows(shorts)
        got = {label for _, kind, label in tw.find(searched) if kind == "whole"}
        toks = re.findall(r"\w+", html.unescape(searched).lower())
        expected = {label for label, t in shorts if sum(1 for w in t.split() if lettered(w)) >= 3 and len(t) >= 12
                    and any(toks[i:i + len(t.split())] == t.split() for i in range(len(toks)))}
        assert got == expected, (shorts, searched)


def test_offsets_point_into_the_searched_text():
    tw = npv.TextWindows([("T", ISSUE_TEXT)])
    blob = "a\n" * 5 + json.dumps({"k": ISSUE_TEXT})
    found = tw.find(blob)
    assert found and npv.line_number(blob, found[0][0]) == 6
    assert blob[found[0][0]:found[0][0] + 10] in json.dumps(ISSUE_TEXT)
    tw = npv.TextWindows([("S", REPLY_TEXT)])
    page = "<p>x</p>\n<p>" + REPLY_TEXT.replace("None", "<b>None</b>") + "</p>"
    found = tw.find(page)
    assert [(npv.line_number(page, k), kind) for k, kind, _ in found] == [(2, "whole")]


def test_library_frames_boilerplate_and_repositories():
    assert npv.thread_segments("before\n" + LIB_FRAME + "after") == ["before\n", "after"]
    assert npv.library_frames(USER_FRAME) == []
    crlf = LIB_FRAME.replace("\n", "\r\n")
    assert npv.library_frames("x\r\n" + crlf) == [(3, 3 + len(crlf))]
    banner = "x\n====== 2 failed, 1 passed in 0.12s ======\ny\n"
    assert npv.thread_segments(banner) == ["x\n", "y\n"]
    generic = npv.generic_lines(["import sys\nimport os\n"])
    assert npv.thread_segments("A\n+import sys\n import os\nB\n", generic=generic) == ["A\n", "B\n"]
    assert npv.thread_segments("A\nimport fxnat\nB\n", generic=generic) == ["A\nimport fxnat\nB\n"]
    assert npv.parse_repository("https://github.com/fx-org/fx-widgets") == ("fx-org", "fx-widgets")
    assert npv.parse_repository("https://api.github.com/repos/fx-org/fx-widgets.git") == ("fx-org", "fx-widgets")
    assert npv.parse_repository("not a url") is None


def test_missing_natural_texts_are_refused(tmp_path, tasks_root, screening):
    texts, _ = screening
    with pytest.raises(SystemExit, match="--natural-texts"):
        scan.main("--natural-texts", str(tmp_path / "missing"), "--screening-texts", str(texts))
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="--natural-texts: .* holds no task directory"):
        scan.main("--natural-texts", str(tmp_path / "empty"), "--screening-texts", str(texts))
    # A root one level too high (data/natural: tasks/ and snapshots/) or too low (one task: candidates/, contracts/ ...)
    # holds directories but no task: refused, not read as tasks that hold nothing.
    for wrong in (tasks_root.parent, tasks_root / "NP-90"):
        with pytest.raises(FileNotFoundError, match="holds no natural task"):
            scan.natural_material(wrong)
        with pytest.raises(SystemExit, match="--natural-texts: .* holds no natural task"):
            scan.main("--natural-texts", str(wrong), "--screening-texts", str(texts))


NATURAL_FINDING = re.compile(r": (?:natural (?:text window|short text|repository (?:name|owner in a URL))|check id of a "
                             r"natural task|code line of a natural task(?:'s base snapshot)?)(?: |$)")


@pytest.mark.skipif(not (ROOT / "data" / "natural" / "tasks").is_dir(),
                    reason="the natural tasks are git-ignored and exist only where the natural arm was built")
def test_the_repository_passes_against_its_natural_tasks(capsys):
    """No natural finding in the working tree or in the file versions and metadata a push would send, against every
    task directory of the natural arm (both samples' families, the extension's half-built ones included) and their base
    snapshots. The generic rules' findings in commits already pushed (STATUS.md) are another matter: a checkout whose
    branch has no upstream scans the whole history."""
    scan.main("--natural-texts", "data/natural/tasks")
    out = capsys.readouterr().out.strip().splitlines()
    natural_findings = [line for line in out[:-1] if NATURAL_FINDING.search(line)]
    assert natural_findings == [], f"{len(natural_findings)} natural finding(s), first: {natural_findings[:3]}"
    tasks = sorted(p.name for p in (ROOT / "data" / "natural" / "tasks").iterdir() if p.is_dir())
    assert out[-1].startswith("scan: ") and f"natural texts of {len(tasks)} task(s)" in out[-1]
    assert NATURAL_FINDING.search("x.md:3: natural short text (NP-03)") and not NATURAL_FINDING.search(
        "x.md:3: session-local path")
    assert NATURAL_FINDING.search("x.md:3: code line of a natural task's base snapshot (NP-10)")


def test_reference_test_is_a_natural_code_line_source():
    """The fixture's B1 overlay holds UPSTREAM_LINE, so the code-line tests above read an upstream test line."""
    assert UPSTREAM_LINE in REFERENCE_TEST
