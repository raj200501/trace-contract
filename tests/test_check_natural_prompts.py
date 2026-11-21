"""scripts/check_natural_prompts.py: the natural arm's prompt templates (experiments/prompts/natural/; decision log D64).

The real templates are parsed, rendered for every variant and compared with their sources in the repository. The
labeler workflow, the source of two of them, lies outside the repository, so here those two are only checked to name
it and to render; the build session compares them with --source-dir. Synthetic scripts and templates check the reader
of the JavaScript sources, the word-level comparison, the header rules, the value rules and --verify.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import textwrap
from pathlib import Path

import pytest

R = Path(__file__).resolve().parents[1]
NAT_WS = "/home/user/nat_ws"


def _load(name: str):
    """A script as a module (registered first: its dataclasses look their module up)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, R / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cnp = _load("check_natural_prompts")

EXPECTED = {"contract:v1-natural", "testgen:v1-natural", "b3:v1", "attack:v1-natural", "alt:v1-natural",
            "revise:v1-natural", "refcontract:v1", "refcheck:v1-natural", "review:v1-natural", "fix:v1-natural",
            "labeler:v1-natural", "labeler-revise:v1-natural", "altimpl:v1-natural", "nearmiss:v1-natural",
            "mapper:v1-natural"}
OUTSIDE = {"labeler:v1-natural", "labeler-revise:v1-natural"}  # their source script is not in the repository
# Each template's workspace, named as the pre-flight names the agents' audit entries (preflight_final_run.py).
ROLE = {"contract:v1-natural": "contract-full", "testgen:v1-natural": "testgen-initial", "b3:v1": "diff-derived",
        "attack:v1-natural": "attack-initial", "alt:v1-natural": "alt-initial", "revise:v1-natural": "revise-initial-1",
        "refcontract:v1": "refcontract", "refcheck:v1-natural": "refcheck", "review:v1-natural": "refcheck-review-1",
        "fix:v1-natural": "refcheck-fix-1", "labeler:v1-natural": "labeler", "labeler-revise:v1-natural": "labeler-revision",
        "altimpl:v1-natural": "eval-alt-1", "nearmiss:v1-natural": "eval-nm-1", "mapper:v1-natural": "mapper-1"}


def _findings(*messages: str) -> str:
    """FINDINGS in its canonical form: each finding's code and message, as json.dumps(indent=1)."""
    return json.dumps([{"code": "attack_not_caught", "message": m} for m in messages], indent=1, ensure_ascii=False)


def _issues(**change) -> str:
    """ISSUES in its canonical form: the review schema's five keys, as compact JSON."""
    issue = {"test": "test_x", "kind": "over_specified", "requirement_ids": ["R1"], "explanation": "it fixes a name",
             "suggested_fix": "check the value only", **change}
    return json.dumps([issue], ensure_ascii=False, separators=(",", ":"))


SAMPLE = {"TASK": "NP-03", "SESSION_ID": "aidev-pr-123456789", "PYTHONPATH": "/work/src:/work", "PYPATH": "/repo/src:/repo",
          "TESTS": "-q tests/test_example.py", "TARGET": "R2", "ITER": "1",
          "FINDINGS": _findings("a development attack passes"), "ISSUES": _issues(),
          "VALIDATION": "reference, 3 repeats: pass, pass, pass\ndev no-op: task_failure\nchecks failing on the reference: none",
          "FAILING": "test_checks.py::test_parse_empty\ntest_checks.py::test_round_trip"}


def _values(t, **extra) -> dict[str, str]:
    """Host values for every placeholder of ``t`` that no variant fixes."""
    fixed = {n for vs in t.variants.values() for n in vs} | {s.placeholder for s in t.sections if s.kind == "value"}
    vals = {k: SAMPLE[k] for k in t.placeholders if k in SAMPLE and k not in fixed}
    if "WS" in t.placeholders:
        vals["WS"] = f"{NAT_WS}/NP-03/{ROLE[t.name]}"
    return {**vals, **extra}


def _renders(t) -> dict[str | None, str]:
    return {v: cnp.render(t, variant=v, values=_values(t)) for v in (sorted(t.variants) or [None])}


# --------------------------------------------------------------------------- the real templates


@pytest.fixture(scope="module")
def templates():
    return cnp.load_templates()


def test_the_template_set_is_complete_and_each_names_its_source(templates):
    assert {t.name for t in templates} == EXPECTED
    for t in templates:
        assert t.sha256 == hashlib.sha256(t.path.read_bytes()).hexdigest()
        assert t.comments[0].startswith(f"# Natural-arm prompt template {t.name} (decision log {cnp.DECISION}; ")
        assert any(c.startswith("# Source template:") for c in t.comments)
        for letter in t.deviations:
            assert any(f"({letter})" in c for c in t.comments), (t.name, letter)
        if t.name in OUTSIDE:
            assert "/" not in t.fields["source-file"]  # a bare file name: no session-local path in the repository
        else:
            assert t.fields["source-file"].startswith("experiments/prompts/workflows/")


def test_the_templates_cite_one_decision_log_entry_which_no_other_entry_holds():
    """Every template, the README and the checker cite the entry that fixes the recipe by one number, and the decision
    log either does not hold that number yet or holds the recipe there (D62 and D63 were taken by other entries)."""
    for p in sorted(cnp.TEMPLATES.iterdir()):
        if p.suffix in (".txt", ".md"):
            assert set(re.findall(r"decision log (D\d+)", p.read_text(encoding="utf-8"))) == {cnp.DECISION}, p.name
    assert f"decision log {cnp.DECISION}" in cnp.__doc__
    log = (R / "docs" / "decision_log.md").read_text(encoding="utf-8")
    heading = re.search(rf"^### {cnp.DECISION}\. (.*)$", log, re.MULTILINE)
    assert heading is None or "natural-arm recipe" in heading.group(1), heading.group(0)


def test_every_template_outside_its_deviations_is_its_source_word_for_word(templates):
    rows = {r["name"]: r for r in cnp.summarize(cnp.TEMPLATES, [], allow_missing=True)}
    for name, r in rows.items():
        assert r["problems"] == [], (name, r["problems"])
        if name in OUTSIDE:
            assert r["source"] == "not available" and len(r["notes"]) == 1, (name, r["notes"])
            continue
        assert r["notes"] == [], (name, r["notes"])
        assert r["source"] == "checked"
        assert r["sections"] and all(s["kept_words"] > 0 or s["source_spec"] is None for s in r["sections"])
        body = next(s for s in r["sections"] if s["section"] == "body")
        changed = sum(d["removed"] for d in body["deviations"])
        assert body["kept_words"] + changed == body["source_words"], name  # every source word is kept or in a deviation


def test_a_template_whose_source_lies_outside_fails_unless_allowed(templates):
    rows = {r["name"]: r for r in cnp.summarize(cnp.TEMPLATES, [])}
    for name in OUTSIDE:
        assert rows[name]["source"] == "missing" and len(rows[name]["problems"]) == 1
    assert all(not rows[n]["problems"] for n in EXPECTED - OUTSIDE)


def test_every_variant_renders_without_markers_or_template_placeholders(templates):
    for t in templates:
        for variant, prompt in _renders(t).items():
            assert "{{" not in prompt and "{/}}" not in prompt, (t.name, variant)
            left = set(re.findall(r"\{([A-Z][A-Z0-9_]*)\}", prompt)) & set(cnp.PLACEHOLDERS)
            assert not left, (t.name, variant, left)
            assert not prompt.endswith("\n"), (t.name, variant)


def test_prompts_run_only_the_allowlisted_cli_calls_by_absolute_path(templates):
    """The natural-agent audit allows the CLI only as <repo>/.venv/bin/tracecontract lint-tests|check-proposals."""
    for t in templates:
        for variant, prompt in _renders(t).items():
            assert not re.search(r"(?<!/home/user/trace-contract/)\.venv/bin/tracecontract", prompt), (t.name, variant)
            for m in re.finditer(re.escape(cnp.CLI_PATH) + r"(,|\s+(\S+))", prompt):
                # the preamble names it (followed by a comma); every other mention is a call
                assert m.group(1) == "," or m.group(2) in ("lint-tests", "check-proposals"), (t.name, m.group(0))
            for sub in ("lint-tests", "check-proposals"):  # a prompt that asks for a call names it in full
                if sub in prompt:
                    assert f"{cnp.CLI_PATH} {sub} " in prompt, (t.name, variant, sub)
            for sub in ("export-gen-workspace", "build-verifier", "add-candidate", "make-contract", "sandbox-python",
                        "render-session", "freeze"):
                assert sub not in prompt, (t.name, variant, sub)


def test_prompts_name_no_task_directory_old_workspace_or_held_out_id(templates):
    for t in templates:
        for variant, prompt in _renders(t).items():
            for bad in ("data/natural", "tasks/NP-", "gen_workspaces", "NP-03-eval", "NP-03-pre-review",
                        "claude-code-subagent", "Context about the project owner", "Commands run from"):
                assert bad not in prompt, (t.name, variant, bad)
            ws = f"{NAT_WS}/NP-03/{ROLE[t.name]}"
            assert ws in prompt, (t.name, variant)
            # the private run records and the repository's worktree are named in the do-not-read list, as directories
            assert "/home/user/nat_runrec" in prompt and "/home/user/tc_analysis_wt" in prompt, (t.name, variant)
            assert not re.search(r"nat_runrec/[\w.-]", prompt), (t.name, variant)


def test_every_host_placeholder_has_a_pattern_or_a_form_check():
    for name, rule in cnp.PLACEHOLDERS.items():
        assert rule.template or rule.pattern is not None or rule.form is not None, name
        assert rule.form is None or rule.form in cnp.FORM_CHECKS, name


def test_the_two_mappers_differ_only_in_their_label(templates):
    t = next(x for x in templates if x.name == "mapper:v1-natural")
    one, two = (cnp.render(t, variant=v, values=_values(t)) for v in ("mapper-1", "mapper-2"))
    assert one.replace("model:config-A:mapper:v1", "M") == two.replace("model:config-A:mapper:v1#2", "M")


def test_variants_differ_only_in_what_they_fix(templates):
    by = {t.name: t for t in templates}
    c = by["contract:v1-natural"]
    full, first = (cnp.render(c, variant=v, values=_values(c)) for v in ("full_session", "initial_only"))
    assert first == full.replace('"full_session"', '"initial_only"').replace("/session.txt", "/session_first_prompt.txt")
    a = by["altimpl:v1-natural"]
    one, two = (cnp.render(a, variant=v, values=_values(a)) for v in ("eval-alt-1", "eval-alt-2"))
    style1, style2 = (cnp.strip_markers(a.value("STYLE", k).text)[0] for k in ("1", "2"))
    assert one.replace("#1", "#2").replace(style1, style2) == two


def test_a_near_miss_that_shares_its_target_is_told_so_by_a_fixed_sentence_only(templates):
    """No near-miss agent is given another's output (decision log D64, deviation h): the shared-target variant adds one
    fixed sentence, and nothing else differs."""
    t = next(x for x in templates if x.name == "nearmiss:v1-natural")
    assert "DONE" not in t.placeholders and set(t.variants) == {"own-target", "shared-target"}
    own, shared = (cnp.render(t, variant=v, values=_values(t)) for v in ("own-target", "shared-target"))
    sentence = cnp.strip_markers(t.value("SHARED", "shared").text)[0].replace("{TARGET}", "R2")
    assert sentence.startswith(" Another near miss") and "R2" in sentence
    assert shared == own.replace("chosen by the host.", "chosen by the host." + sentence, 1) != own
    assert "Do not run the repository's tests" in own


def test_the_labeler_revision_takes_bare_sorted_check_ids_only(templates):
    t = next(x for x in templates if x.name == "labeler-revise:v1-natural")
    names = "test_a.py::test_one\ntest_a.py::test_two\ntest_b.py::TestC::test_three"
    assert names in cnp.render(t, values=_values(t, FAILING=names))
    assert "left uncovered" not in cnp.render(t, values=_values(t))
    for bad in ("fails on reference: test_a.py::test_one", "test_a.py::test_two\ntest_a.py::test_one",
                "test_a.py::test_one\ntest_a.py::test_one", "R4", "test_a.py::test_one\nR4", "test_one",
                "test_a.py::test_one (AssertionError)"):
        with pytest.raises(cnp.TemplateError, match="FAILING"):
            cnp.render(t, values=_values(t, FAILING=bad))


def test_the_host_s_structured_values_must_have_their_form(templates):
    by = {t.name: t for t in templates}
    review, fix, revise = by["review:v1-natural"], by["fix:v1-natural"], by["revise:v1-natural"]
    ok = "reference, 3 repeats: pass, task_failure, pass\ndev no-op: task_failure\n" \
         "checks failing on the reference: test_a.py::test_x, test_a.py::test_y"
    assert ok in cnp.render(review, values=_values(review, VALIDATION=ok))
    for bad in (ok.replace("test_a.py::test_x, test_a.py::test_y", "test_a.py::test_y, test_a.py::test_x"),
                ok.replace("test_a.py::test_y", "test_a.py::test_x"),
                ok.replace("task_failure, pass\n", "pass, pass\n", 1),  # every repeat passed, yet checks failed
                ok.replace("test_a.py::test_y", "test_a.py::test_y (AssertionError)"),
                "reference, 2 repeats: pass, pass\ndev no-op: task_failure\nchecks failing on the reference: none",
                "the reference passed; the no-op failed"):
        with pytest.raises(cnp.TemplateError, match="VALIDATION"):
            cnp.render(review, values=_values(review, VALIDATION=bad))
    assert _issues() in cnp.render(fix, values=_values(fix))
    for bad in (_issues(kind="style"), _issues(requirement_ids="R1"), "not json", _issues()[1:-1],
                json.dumps(json.loads(_issues()), indent=1), _issues().replace('"suggested_fix"', '"fix"')):
        with pytest.raises(cnp.TemplateError, match="ISSUES"):
            cnp.render(fix, values=_values(fix, ISSUES=bad))
    for bad in (json.dumps(json.loads(_findings("x")), separators=(",", ":")),
                json.dumps([{"message": "x", "code": "y"}], indent=1),
                json.dumps([{"code": "y", "message": "x", "candidate_id": "NP-03-reference"}], indent=1),
                json.dumps([{"code": "y", "message": 3}], indent=1), "[]x"):
        with pytest.raises(cnp.TemplateError, match="FINDINGS"):
            cnp.render(revise, variant="full_audited", values=_values(revise, FINDINGS=bad))


def test_the_template_files_pass_the_tracked_file_scan():
    scan = _load("scan_tracked_files")
    for p in [*sorted(cnp.TEMPLATES.iterdir()), R / "scripts" / "check_natural_prompts.py", Path(__file__)]:
        assert scan.scan_text(p.read_text(encoding="utf-8"), p.name, []) == 0, p.name


def test_the_rendering_version_is_the_pr_thread_renderers():
    from tracecontract.ingest.github_pr import PR_THREAD_BANNER, PR_THREAD_HEADERS

    v = cnp.rendering_version()
    assert v["banner_sha256"] == hashlib.sha256(PR_THREAD_BANNER.encode()).hexdigest()
    assert v["headers"] == PR_THREAD_HEADERS


# --------------------------------------------------------------------------- reading the JavaScript sources

JS = textwrap.dedent(r"""
    const T = args.task
    const CLI = '.venv/bin/tracecontract'
    const WS = `${args.ws_root}/${T}`
    const PRE = [
      'Line one of the preamble.',
      "Working directory: " + '/home/user/repo' + ' (it\'s the repo).',
    ].join('\n')
    function noRead(own) {
      return 'Do NOT read ' + own + ' or the repository.'
    }
    const GREET = (name) => `Hello ${name}, run \`${CLI} lint-tests <dir>\` and "try:\\n    f(0)" in ${WS}/x.`
    const items = [
      { id: 'one', text: 'First item text.', note: `A note for ${T}` },
    ]
    const style = it.k === 1
      ? 'The first style.'
      : 'The second style.'
    function genPrompt(it) {
      if (it.kind === 'x') {
        return PRE + '\n\nTASK: do ' + it.what + ' for ' + T + '. ' + noRead(ws) +
          '\nReturn ' + JSON.stringify(it.list, null, 1) + '.'
      }
      return 'two statements'; const z = 1
    }
""").lstrip("\n")


def _line(needle: str) -> int:
    return next(n for n, line in enumerate(JS.split("\n"), 1) if needle in line)


def test_a_template_literal_with_escapes_and_interpolations():
    src = cnp.SourceText(JS, {"CLI": f"L{_line('const CLI')}", "WS": f"L{_line('const WS')}"}, {"T": "TASK"})
    assert src.flatten(f"L{_line('const GREET')}") == ('Hello ${name}, run `.venv/bin/tracecontract lint-tests <dir>` and '
                                                      '"try:\\n    f(0)" in ${args.ws_root}/{TASK}/x.')
    assert src.used == {"CLI", "WS", "T"}


def test_concatenation_join_functions_and_maps():
    a, b = _line("return PRE"), _line("JSON.stringify")
    src = cnp.SourceText(JS, {"PRE": f"L{_line('const PRE')}-L{_line('].join')}",
                              "noRead": f"L{_line('function noRead')}-L{_line('function noRead') + 2}"},
                         {"T": "TASK", "it.what": "WHAT", "own": "WS"})
    assert src.flatten(f"L{a}-L{b}") == ("Line one of the preamble.\nWorking directory: /home/user/repo (it's the repo).\n\n"
                                         "TASK: do {WHAT} for {TASK}. Do NOT read {WS} or the repository.\n"
                                         "Return ${JSON.stringify(it.list,null,1)}.")


def test_key_and_literal_selectors():
    src = cnp.SourceText(JS, {}, {"T": "TASK"})
    n = _line("id: 'one'")
    assert src.flatten(f"L{n}:text") == "First item text."
    assert src.flatten(f"L{n}:note") == "A note for {TASK}"
    assert src.flatten(f"L{_line('? ')}#1") == "The first style."
    assert src.flatten(f"L{_line(': ' + chr(39) + 'The second')}#1") == "The second style."


def test_bad_specs_are_refused():
    src = cnp.SourceText(JS, {}, {})
    with pytest.raises(cnp.SourceError, match="more than one statement"):
        src.flatten(f"L{_line('two statements')}")
    with pytest.raises(cnp.SourceError, match="lines"):
        src.flatten("L900")
    with pytest.raises(cnp.SourceError, match="no key"):
        src.flatten(f"L{_line('id:')}:missing")
    with pytest.raises(cnp.SourceError, match="bad source spec"):
        src.flatten("line 3")


# --------------------------------------------------------------------------- the word-level comparison

SOURCE = "Read the file A.\nThen run the command B on it, and return the output C."


def test_identical_text_is_kept_word_for_word_whatever_the_line_breaks():
    c = cnp.compare_section(SOURCE, "Read the file A. Then run\nthe command B on it,   and return the output C.")
    assert (c.problems, c.hunks, c.kept_words, c.source_words) == ([], [], 16, 16)


def test_an_unmarked_insertion_or_removal_is_a_problem():
    assert cnp.compare_section(SOURCE, "Read the file A. Then run the command B on it, and return the full output C.").problems
    assert cnp.compare_section(SOURCE, "Read the file A. Then run the command B on it, and return C.").problems
    assert cnp.compare_section(SOURCE, "Read the file A. Then run the command B on it, and return the output C. More.").problems
    assert cnp.compare_section(SOURCE, "Read file A. Then run the command B on it, and return the output C.").problems


def test_marked_changes_report_what_they_remove_and_add():
    c = cnp.compare_section(SOURCE, "Read the file {{a}}X.{{/}} Then run the command {{b}}{{/}}on it, and return the "
                                    "{{b,c}}checked output{{/}} C.")
    assert c.problems == []
    assert [(h.letters, h.removed, h.added) for h in c.hunks] == [
        (("a",), ["A."], ["X."]), (("b",), ["B"], []), (("b", "c"), ["output"], ["checked", "output"])]


def test_a_word_touching_a_marker_belongs_to_the_deviation():
    c = cnp.compare_section(SOURCE, "Read the file A. Then run the command {{a}}D{{/}}, and return the output C.")
    assert c.problems == [] and c.hunks[0].removed == ["B", "on", "it,"] and c.hunks[0].added == ["D,"]


def test_new_text_must_lie_wholly_in_deviations():
    assert cnp.compare_section(None, "{{j}}All of it is new.{{/}}").problems == []
    assert cnp.compare_section(None, "{{j}}Part of it{{/}} is not marked.").problems


def test_a_marker_that_changes_nothing_is_noted():
    c = cnp.compare_section(SOURCE, "Read the file {{a}}A.{{/}} Then run the command B on it, and return the output C.")
    assert c.problems == [] and "equals the source text" in c.notes[0]


def test_markers_must_be_well_formed():
    for bad in ("{{a}}open", "close{{/}}", "{{a}}{{b}}nested{{/}}{{/}}", "{{A}}upper{{/}}", "{{a b}}x{{/}}"):
        with pytest.raises(cnp.TemplateError):
            cnp.strip_markers(bad)


# --------------------------------------------------------------------------- template files


def _template(tmp: Path, body: str, *, fields: str = "", extra: str = "", sha: str | None = None,
              comments: str = "# (a) a path changed.") -> Path:
    (tmp / "src.js").write_text("const T = args.task\nconst P = `Work in ${T} under /old/ws now.`\n", encoding="utf-8")
    sha = sha or hashlib.sha256((tmp / "src.js").read_bytes()).hexdigest()
    text = (f"# Natural-arm prompt template demo:v1 (test).\n# Source template: P of a test script.\n{comments}\n\n"
            f"name: demo:v1\nformat: natural-template/1\nsource-file: src.js\nsource-sha256: {sha}\n"
            f"source-map: T=TASK\ndeviations: a\nplaceholders: TASK WS\n{fields}\n@@ body <- L2\n{body}\n{extra}")
    p = tmp / "demo_v1.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_a_well_formed_template_compares_and_renders(tmp_path):
    p = _template(tmp_path, "Work in {TASK} under {{a}}{WS}{{/}} now.")
    [row] = cnp.summarize(tmp_path, [tmp_path])
    assert row["problems"] == [] and row["source"] == "checked"
    line = p.read_text(encoding="utf-8").split("\n").index("@@ body <- L2") + 2  # the body's first line
    assert row["sections"][0]["deviations"] == [{"letters": "a", "line": line, "removed": 1, "added": 1}]
    prompt = cnp.render(cnp.parse_template(p), values={"TASK": "NP-07", "WS": f"{NAT_WS}/NP-07/demo"})
    assert prompt == f"Work in NP-07 under {NAT_WS}/NP-07/demo now."


def test_a_changed_source_fails_the_summary(tmp_path):
    _template(tmp_path, "Work in {TASK} under {{a}}{WS}{{/}} now.", sha="0" * 64)
    [row] = cnp.summarize(tmp_path, [tmp_path])
    assert row["source"] == "changed" and "not the header's" in row["problems"][0]


def test_an_unmarked_difference_fails_the_summary(tmp_path):
    _template(tmp_path, "Work in {TASK} {{a}}{WS}{{/}} now, please.")
    [row] = cnp.summarize(tmp_path, [tmp_path])
    assert any("unmarked difference" in x for x in row["problems"])


@pytest.mark.parametrize("change, match", [
    ({"comments": "# no letter described here"}, "does not describe"),
    ({"body": "Work in {TASK} under {{b}}{WS}{{/}} now."}, "not in the header's deviations"),
    ({"body": "Work in {TASK} under {WS} now."}, "marked nowhere"),
    ({"body": "Work in {TASK} under {{a}}{WS} {OTHER}{{/}} now."}, "undeclared placeholders"),
    ({"body": "Work in {TASK} under {{a}}the old place{{/}} now."}, "not used"),
    ({"fields": "variant x: NOPE=1"}, "undeclared placeholder NOPE"),
])
def test_malformed_templates_are_refused(tmp_path, change, match):
    kw = {"body": "Work in {TASK} under {{a}}{WS}{{/}} now.", **change}
    with pytest.raises(cnp.TemplateError, match=match):
        cnp.parse_template(_template(tmp_path, **kw))


def test_a_header_without_its_source_is_refused(tmp_path):
    p = _template(tmp_path, "Work in {TASK} under {{a}}{WS}{{/}} now.")
    p.write_text(p.read_text().replace("# Source template: P of a test script.\n", ""), encoding="utf-8")
    with pytest.raises(cnp.TemplateError, match="names no source template"):
        cnp.parse_template(p)


# --------------------------------------------------------------------------- rendering


@pytest.fixture()
def demo(tmp_path):
    return cnp.parse_template(_template(tmp_path, "Work in {TASK} under {{a}}{WS}{{/}} now."))


def test_every_placeholder_needs_a_valid_value(demo):
    ws = f"{NAT_WS}/NP-07/demo"
    with pytest.raises(cnp.TemplateError, match="no value"):
        cnp.render(demo, values={"TASK": "NP-07"})
    with pytest.raises(cnp.TemplateError, match="has no placeholder"):
        cnp.render(demo, values={"TASK": "NP-07", "WS": ws, "TARGET": "R1"})
    with pytest.raises(cnp.TemplateError, match="does not match"):
        cnp.render(demo, values={"TASK": "CS-01", "WS": ws})
    with pytest.raises(cnp.TemplateError, match="not a workspace of NP-07"):
        cnp.render(demo, values={"TASK": "NP-07", "WS": f"{NAT_WS}/NP-08/demo"})
    with pytest.raises(cnp.TemplateError, match="does not match"):
        cnp.render(demo, values={"TASK": "NP-07", "WS": "/home/user/trace-contract/data/x"})


def test_host_values_are_data_and_template_values_are_not_the_hosts(templates, demo):
    t = next(x for x in templates if x.name == "revise:v1-natural")
    text = _findings("the {TASK} of {WS}")
    vals = _values(t, FINDINGS=text)
    assert text in cnp.render(t, variant="full_audited", values=vals)
    with pytest.raises(cnp.TemplateError, match="fixed by the template"):
        cnp.render(t, variant="full_audited", values={**vals, "VARIANT": "initial_only"})
    with pytest.raises(cnp.TemplateError, match="give --variant"):
        cnp.render(t, values=vals)
    with pytest.raises(cnp.TemplateError, match="no variant"):
        cnp.render(t, variant="nope", values=vals)
    # A host value that starts with "@" is data: it never names one of the template's value sections.
    with pytest.raises(cnp.TemplateError, match="does not match"):
        cnp.render(demo, values={"TASK": "NP-07", "WS": "@body"})


def test_a_template_value_cannot_come_from_the_host(tmp_path):
    p = _template(tmp_path, "Work in {TASK} under {{a}}{WS} {STYLE}{{/}} now.")
    p.write_text(p.read_text().replace("placeholders: TASK WS", "placeholders: TASK WS STYLE"), encoding="utf-8")
    with pytest.raises(cnp.TemplateError, match="the template's value"):
        cnp.render(cnp.parse_template(p), values={"TASK": "NP-07", "WS": f"{NAT_WS}/NP-07/demo", "STYLE": "free text"})


def test_a_prompt_naming_forbidden_material_is_refused(templates):
    t = next(x for x in templates if x.name == "revise:v1-natural")
    session_path = "/tmp/claude-0/" + "-home-x/scratchpad"
    tier = "hai" + "ku"
    for bad in ("see data/natural/tasks/NP-03", session_path, "NP-03-eval-nm-1 passes", f"written by {tier}",
                "cla" + "ude-9-" + "son" + "net", "/home/user/nat_runrec/NP-03/refcheck.json", "eval-nm-1 passes",
                "the pre-review state passes"):
        with pytest.raises(cnp.TemplateError, match="names"):
            cnp.render(t, variant="full_audited", values=_values(t, FINDINGS=_findings(bad)))
    # an ordinary word that the pseudonymiser's list of tier names also holds is not refused
    assert "an instant timeout" in cnp.render(t, variant="full_audited", values=_values(t, FINDINGS=_findings("an instant timeout")))


def test_the_tier_words_are_the_pseudonymisers_but_the_ordinary_word():
    from tracecontract.ingest.pseudonymize_pr import _TIER

    assert set(cnp.TIER_WORDS) == set(re.fullmatch(r"\(\?:(.*)\)", _TIER).group(1).split("|")) - {"instant"}
    assert len(cnp.TIER_WORDS) >= 3 and "instant" not in cnp.TIER_WORDS
    assert cnp.MODEL.search("written by claude-" + "instant-1.2")  # a model named with it is still a model identifier


def test_a_prompt_naming_a_cli_call_outside_the_allowlist_is_refused(templates):
    t = next(x for x in templates if x.name == "revise:v1-natural")
    ok = f"then {cnp.CLI_PATH} lint-tests {NAT_WS}/NP-03/revise-initial-1/tests"
    assert ok in cnp.render(t, variant="full_audited", values=_values(t, FINDINGS=_findings(ok)))
    for bad, why in ((".venv/bin/tracecontract lint-tests x", "relative path"), (f"{cnp.CLI_PATH} grade x", "other than"),
                     (f"{cnp.CLI_PATH}", "other than")):
        with pytest.raises(cnp.TemplateError, match=why):
            cnp.render(t, variant="full_audited", values=_values(t, FINDINGS=_findings(bad)))
    assert cnp.cli_problems(f"of the study's CLI, {cnp.CLI_PATH}, run nothing but") == []


# --------------------------------------------------------------------------- the command line


def test_render_prints_the_sha256_and_verifies_a_sent_prompt(tmp_path, capsys, demo):
    args = ["render", str(demo.path), "--set", "TASK=NP-07", "--set", f"WS={NAT_WS}/NP-07/demo"]
    prompt = f"Work in NP-07 under {NAT_WS}/NP-07/demo now."
    out = tmp_path / "p.txt"
    assert cnp.main([*args, "--out", str(out)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert report["template_sha256"] == demo.sha256 and out.read_text(encoding="utf-8") == prompt
    assert cnp.main([*args, "--out", str(out)]) == 1  # a prompt file is never overwritten
    capsys.readouterr()
    assert cnp.main([*args, "--verify", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["verify"] == "equal"
    other = tmp_path / "q.txt"
    other.write_text(prompt.replace("now", "then"), encoding="utf-8")
    assert cnp.main([*args, "--verify", str(other)]) == 1
    assert "line 1, column" in json.loads(capsys.readouterr().out)["verify"]


def test_a_framed_workflow_prompt_reads_as_the_run_record_reads_it(tmp_path, capsys, demo):
    """--verify accepts a workflow agent's first message, and the hash is the run record's prompt_sha256."""
    arr = _load("agent_run_record")

    def frame(text: str) -> str:
        return ("[Workflow harness — computed task] The task text below was computed at runtime. "
                "The computed task text follows:\n" + "\n".join(("  " + x) if x else x for x in text.split("\n")))

    several = "first line\n\n  indented line\nlast line"
    assert arr.computed_task(frame(several)) == cnp.sent_prompt(frame(several)) == several
    assert cnp.sent_prompt(several) == several
    prompt = cnp.render(demo, values={"TASK": "NP-07", "WS": f"{NAT_WS}/NP-07/demo"})
    (tmp_path / "framed.txt").write_text(frame(prompt), encoding="utf-8")
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"prompt_sha256": cnp.sha256_text(prompt)}), encoding="utf-8")
    args = ["render", str(demo.path), "--set", "TASK=NP-07", "--set", f"WS={NAT_WS}/NP-07/demo"]
    assert cnp.main([*args, "--verify", str(tmp_path / "framed.txt"), "--record", str(record)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["verify"], report["record"]) == ("equal", "equal")
    record.write_text(json.dumps({"prompt_sha256": "0" * 64}), encoding="utf-8")
    assert cnp.main([*args, "--record", str(record)]) == 1
    assert "not the rendering's" in json.loads(capsys.readouterr().out)["record"]


def test_values_from_files_and_json(tmp_path, capsys, templates):
    t = next(x for x in templates if x.name == "labeler-revise:v1-natural")
    failing = "test_a.py::test_one\ntest_a.py::test_two"
    (tmp_path / "failing.txt").write_text(failing)
    ws = f"{NAT_WS}/NP-03/labeler-revision"
    (tmp_path / "values.json").write_text(json.dumps({"TASK": "NP-03", "WS": ws}))
    assert cnp.main(["render", str(t.path), "--values", str(tmp_path / "values.json"),
                     "--set-file", f"FAILING={tmp_path / 'failing.txt'}"]) == 0
    expected = cnp.render(t, values={"TASK": "NP-03", "WS": ws, "FAILING": failing})
    assert json.loads(capsys.readouterr().out)["prompt_sha256"] == cnp.sha256_text(expected)
    assert cnp.main(["render", str(t.path), "--values", str(tmp_path / "values.json"), "--set", "TASK=NP-04",
                     "--set-file", f"FAILING={tmp_path / 'failing.txt'}"]) == 1  # TASK given twice


def test_summary_exit_status(capsys):
    assert cnp.main(["summary", "--allow-missing-sources"]) == 0
    out = capsys.readouterr().out
    assert out.count("result: ok") == len(EXPECTED) and out.count(": not available") == len(OUTSIDE)
    assert cnp.main(["summary"]) == 1
    capsys.readouterr()
    assert cnp.main(["summary", "--json", "--allow-missing-sources"]) == 0
    assert {r["name"] for r in json.loads(capsys.readouterr().out)} == EXPECTED
