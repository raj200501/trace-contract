"""The natural case-study section's template (paper/sections/natural.tex; the restructure plan, part 7) and main.tex's
``\\nrv`` lookup, fixed before any analysis of the natural run exists.

* (a) Every ``\\nrv`` key that the template uses is one that paper/make_tables.py --natural-run writes for a synthetic
  world of the run's six families under their ids (NP-03, NP-04, NP-05, NP-18, NP-19, NP-20), the run's facts, D19's
  labels and each family's cost among them; every ``\\nat`` key is one of the committed screening numbers
  (paper/generated/natural/numbers.tex).
* The premises: the template's fixed sentences state construction facts that the analysis also computes (B1 against the
  regression norm, the labelers, the reference checks' fix rounds, the failed audits, the run's families, invocations,
  revision and pilot flag; decision log D64, D70, D72, D75, D76). The synthetic world is given those facts, so that its
  rendering does not contradict itself, and :func:`template_problems` checks the cells that measure them: here, and on the
  run's own numbers once they are published (the integration check; restructure plan, order of work 4).
* (b) A document with main.tex's preamble (its packages and macros) that inputs the generated numbers and the template
  compiles with pdflatex, with no error, no reference left undefined, no TODO marker and no UNFILLED marker but the one of
  the closing paragraph's integration slot, which the integration replaces. The preamble alone compiles without the
  natural run's numbers, as main.tex does until the run is published.
* (c) The template holds none of the words that the plan bans (part 2; "how often" only to say that the case studies
  cannot show it), no model identifier, agent-tool name or tier wording, no digit outside a macro or an identifier, no
  count written as a word, and no option written so that it prints as an en dash.
* Its records: every decision-log entry it cites is logged, or is the pending next entry its header declares; the
  disclosures that the records require are in their paragraphs; and its own table defines every term its cells can hold.
* main.tex defines ``\\nrv`` as it defines ``\\fv`` and ``\\nat``, in the form numbers.tex names, inputs
  generated/natural_run/numbers.tex where it exists, and does not input the template yet.

Synthetic fixtures only (tests/test_analysis_natural.py's build_world in a scratch git repository; nothing is graded, no
Docker); they check the template and the code, and are not research evidence. The construction facts given to the world
are those of the decision log; no result of the run is read or assumed. pdflatex writes its build files in pytest's
temporary directory, never in the repository.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from natural_task_layout import B1_CHECKS, BASE_TEST, REFERENCE_TEST, TEST_ARGS
from test_analysis_natural import _audit_record, build_world, d19_note, relabel_d19

from tracecontract.analysis import analyze
from tracecontract.schemas import VerifierSpec
from tracecontract.store import dump, load, write_json

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
TEMPLATE = PAPER / "sections" / "natural.tex"
REAL_NUMBERS = PAPER / "generated" / "natural_run" / "numbers.tex"  # the run's own numbers, once it is published
spec = importlib.util.spec_from_file_location("make_tables_natural_template", PAPER / "make_tables.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

FAMILIES = ("NP-03", "NP-04", "NP-05", "NP-18", "NP-19", "NP-20")  # the run's families, in its order (protocol §20.2)
RUN_KEYS = {"run.date", "run.started", "run.finished", "run.revision", "run.harness", "run.repeats", "run.pilot",
            "run.invocations", "run.families"}
D19_KEYS = ("valid", "invalid", "ambiguous", "unlabeled", "ambiguous.ids", "ambiguous.reasons")
COST_KEYS = ("turns", "toolcalls", "wall", "grading", "s10", "recorded", "artifacts")  # the plan's cost.<family>.*
# The words that the plan's claims checklist bans (part 2): no frequency, quantifier, significance, prevention, ground
# truth, reward fidelity or pre-registration. "how often" may appear only to say that the case studies cannot show it.
BANNED = (r"\bmost\b", r"\bseveral\b", r"\boften\b", r"\bsignifican\w*", r"\bprevent\w*", r"\bground[- ]truth\b",
          r"\breward[- ]fidelity\b", r"\bpre-?registered\b")
HOW_OFTEN = r"\bcannot\s+show\s+how\s+often\b"
# Tier wording beside _check_private's model and agent-product pattern (restructure plan, part 8).
TIER = (r"\btiers?\b", r"\bdefault (?:agent )?model\b", r"\bsmallest\b")
# What the template may hold with digits: macro calls and the arguments of \ref, \label and \input; protocol sections;
# families, conditions, stages, phases, decision-log entries and requirement ids; versions and run ids; the pool's
# candidates; audit:v1; D64's numbered decisions; LaTeX lengths and column widths, and a command's arguments.
IDENTIFIERS = (r"\\(?:nrv|nat|fv|ref|label|input|IfFileExists)\{[^{}]*\}", r"\\S\d+(?:\.\d+)*", r"\bNP-\d+\b",
               r"\b[BCDPRS]\d+a?\b", r"\bnatural-pr-v\d+\b", r"\bv\d+(?:\.\d+)*\b", r"\beval-(?:alt|nm)-\d+\b",
               r"\baudit:v\d+\b", r"\bdecision~\d+\b", r"\{[0-9.]+(?:pt|\\linewidth)\}",
               r"\\providecommand\{\\[A-Za-z]+\}\[\d\]", r"#\d")
NUMBER_WORDS = (r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|half|"
                r"dozen)\b")
# The closing paragraph's integration slot: the one UNFILLED marker the template prints on purpose, until the integration
# writes, from the run's cells, the sentences that name families by them (restructure plan, part 7, item 6).
SLOT = "integration slot: sentences naming the families by their C1 and C3 cells in the table of the pre-review states"


def _fk(family: str) -> str:
    return family.lower().replace("-", "")


# --------------------------------------------------------------------------- the recorded construction facts, and the premises

# The construction facts that the template's sentences state, as the decision log records them; the synthetic world is
# given them (_as_recorded), so that its rendering does not contradict itself.
B1_NORM = dict(zip(FAMILIES, ("yes", "no", "yes", "no", "in part", "yes")))  # D64, decision 3
LABELERS = {"NP-03": ("unusable", 2), "NP-04": ("usable", 1), "NP-05": ("usable", 2), "NP-18": ("usable", 1),
            "NP-19": ("unusable", 2), "NP-20": ("usable", 2)}  # D72, D75: the labeler's status and round
FIX_ROUNDS = {"NP-03": 0, "NP-04": 0, "NP-05": 2, "NP-18": 0, "NP-19": 1, "NP-20": 0}  # D72, D75; every one usable
# D70: C2's and C4's audits, each (revisions, passed, the finding codes of the last iteration)
AUDITS = {"NP-03": ((2, True, []), (3, False, ["reference_not_passing"])),
          "NP-04": ((3, False, ["false_rejection_dev"]), (0, True, [])),
          "NP-05": ((3, False, ["false_acceptance_dev"]), (3, False, ["false_acceptance_dev"])),
          "NP-18": ((1, True, []), (1, True, [])),
          "NP-19": ((2, True, []), (3, False, ["reference_not_passing"])),
          "NP-20": ((1, True, []), (0, True, []))}

# What the template's fixed sentences state about values that the run's analysis also computes: (key, value, the records
# and the sentences). A premise that the run's numbers do not bear out means that those sentences are rewritten from the
# records before anything else is written, never that a cell is changed.
PREMISES: tuple[tuple[str, str, str], ...] = (
    ("run.families", ", ".join(FAMILIES), "protocol §20.2, D76: the first sample's families, each with its paragraph"),
    ("run.invocations", "2", "D76: the status paragraph explains why the first of the run's invocations was stopped"),
    ("run.pilot", "set", "D75, D76: the status paragraph calls the run an automated pilot"),
    *((f"sample.{_fk(f)}", "first", "protocol §20.2: the accepted families of the first sample") for f in FAMILIES),
    *((f"b1.{_fk(f)}.norm", v, "D64, decision 3: the list of differences, and (c)") for f, v in B1_NORM.items()),
    *((f"b1.{_fk(f)}.available", "yes", "D70: (c) speaks of B1's verdicts") for f in ("NP-03", "NP-05", "NP-19", "NP-20")),
    ("il.np03.status", "unusable", "D72: NP-03's first sentence and (d)"),
    ("il.np03.second", "left out", "D72, D76: NP-03's first sentence, (d) and the caveats"),
    ("il.np19.status", "unusable", "D75: NP-19's first sentence and (d)"),
    ("il.np19.round", "2", "D75: NP-19's labeler is unusable after its revision"),
    ("il.np19.second", "left out", "D75, D76: NP-19's first sentence, (d) and the caveats"),
    *((f"il.{_fk(f)}.second", "graded", "D72, D75: (d) gives the family's agreement") for f in ("NP-04", "NP-05", "NP-18", "NP-20")),
    ("il.np20.status", "usable", "D72: NP-20 (f)"),
    ("il.np20.round", "2", "D72: NP-20's labeler is usable after its revision"),
    ("refchecks.np03.rounds", "0", "D72: NP-03 (f), no fix round ran"),
    ("refchecks.np05.rounds", "2", "D75: NP-05 (f), frozen while the last review still asked for fixes"),
    ("refchecks.np18.rounds", "0", "D72: NP-18 (f), no fix round ran"),
    ("refchecks.np19.rounds", "1", "D75: NP-19 (f), the second review after their fix round"),
    ("refchecks.np20.rounds", "0", "D72: NP-20 (f), no fix round ran"),
    ("audit.c4.np03.result", "failed", "D70: NP-03 (f)"),
    ("audit.c2.np04.result", "failed", "D70: NP-04 (f)"),
    ("audit.c2.np05.result", "failed", "D70: NP-05 (f)"),
    ("audit.c4.np05.result", "failed", "D70: NP-05 (f)"),
    ("audit.c4.np19.result", "failed", "D70: NP-19 (f)"),
)


def template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def uncommented(tex: str) -> str:
    """``tex`` without its comments (a % that is not escaped, to the end of its line)."""
    return "\n".join(re.sub(r"(?<!\\)%.*", "", line) for line in tex.splitlines())


def macros(path: Path, prefix: str) -> dict[str, str]:
    """The number macros that a generated numbers.tex defines, by key."""
    return dict(re.findall(rf"^\\expandafter\\gdef\\csname {prefix}:([^\\]+)\\endcsname\{{(.*)\}}$",
                           path.read_text(encoding="utf-8"), re.MULTILINE))


def keys(tex: str, cmd: str) -> set[str]:
    return set(re.findall(rf"\\{cmd}\{{([^{{}}]*)\}}", uncommented(tex)))


def template_problems(numbers: dict[str, str]) -> list[str]:
    """What keeps the template's text from standing on a natural run's numbers (``numbers``: the macros of its
    generated/natural_run/numbers.tex): a key the template uses that is not generated (it would print UNFILLED), a premise
    (:data:`PREMISES`) that the numbers do not bear out, and invocations that name other than one code revision (the
    status paragraph names one)."""
    out = [f"{k}: not generated, so it prints UNFILLED" for k in sorted(keys(template(), "nrv") - numbers.keys())]
    out += [f"{k}: the template states {v!r} ({why}); the numbers hold {numbers.get(k, 'nothing')!r}"
            for k, v, why in PREMISES if numbers.get(k) != v]
    rev = numbers.get("run.revision", "")
    if "," in rev or rev in ("", mt.NOT_RECORDED):
        out.append(f"run.revision: the status paragraph names one code revision; the numbers hold {rev!r}")
    return out


def _as_recorded(run: Path, tasks: list) -> None:
    """Give the synthetic world the construction facts that the template's sentences state: B1 against D19's regression
    norm (:data:`B1_NORM`: the norm's overlay holds B1's test file, that file and another, or the base's), B1 available
    by S10 in every family, the labelers' status records (:data:`LABELERS`), the reference checks' status records, usable
    with their fix rounds (:data:`FIX_ROUNDS`), the audits of C2 and C4 (:data:`AUDITS`), and the run's two invocations at
    one code revision (D76). Nothing else of the world changes."""
    for nt in tasks:
        td, t = nt.task_dir, nt.task_id
        norm = td / "labels" / "base_tests_overlay"
        shutil.rmtree(norm)
        target = norm / TEST_ARGS[-1]
        target.parent.mkdir(parents=True)
        target.write_text(BASE_TEST if B1_NORM[t] == "no" else REFERENCE_TEST, encoding="utf-8")
        if B1_NORM[t] == "in part":
            (target.parent / "test_other.py").write_text(BASE_TEST, encoding="utf-8")
        s10 = json.loads((td / "s10.json").read_text(encoding="utf-8"))
        s10["b1"] = {"available": True, "n_checks": len(B1_CHECKS), "mode": "repo_tests (in_process)"}
        write_json(s10, td / "s10.json")
        status, rnd = LABELERS[t]
        write_json({"status": status, "round": rnd, "reasons": ["synthetic fixture"]},
                   td / "verifiers" / "independent_label" / "status.json")
        write_json({"status": "usable", "fix_rounds": FIX_ROUNDS[t], "reasons": ["synthetic fixture"]},
                   td / "verifiers" / "reference_check" / "status.json")
        for vid, audit in zip(("initial_audited", "full_audited"), AUDITS[t]):
            path = td / "verifiers" / vid / "spec.json"
            dump(load(path, VerifierSpec).model_copy(update={"audit": _audit_record(*audit)}), path)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    first = manifest["invocations"][0]
    manifest["invocations"] = [first, {**first, "at": first["at"].replace(":00:00+", ":00:29+")}]
    write_json(manifest, run / "manifest.json")


def _generate(run: Path, paper: Path) -> Path:
    """The mode's outputs for ``run`` in a stand-in for paper/ (``paper``); returns generated/natural_run."""
    (paper / "generated").mkdir(parents=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mt, "GEN", paper / "generated")
        mp.setattr(mt, "LEDGER", paper / "evidence_ledger.md")
        mt.main(["--natural-run", str(run)])
    return paper / "generated" / "natural_run"


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> Path:
    """A synthetic world of the run's six families under their ids, with their construction records as the decision log
    records them (:func:`_as_recorded`; B3 available in each, D70), and D19 labels with their reasons, two of them
    ambiguous in one family and one in another; analysed."""
    root = tmp_path_factory.mktemp("template")
    run, tasks = build_world(root / "repo", len(FAMILIES), construction=True, task_ids=FAMILIES, b3_taken_out=())
    _as_recorded(run, tasks)
    relabel_d19(tasks[0], "eval-alt-1", "ambiguous", ["REGRESSION"], d19_note("construction valid but checks fail"))
    relabel_d19(tasks[0], "eval-nm-2", "ambiguous", [], d19_note(
        "construction invalid, reference checks pass; the regression norm did not produce a decision"))
    relabel_d19(tasks[3], "eval-nm-1", "ambiguous", [], d19_note(
        "the 3 repeats give different proposals (invalid ['R-corr']; ambiguous []; invalid ['R-corr']): a missing decision"))
    analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    return run


@pytest.fixture(scope="module")
def world(run, tmp_path_factory) -> Path:
    """The mode's outputs (generated/natural_run) for :func:`run`."""
    return _generate(run, tmp_path_factory.mktemp("paper") / "paper")


# --------------------------------------------------------------------------- (a) every key is generated


def test_every_number_key_of_the_template_is_generated(world):
    nrv, generated = keys(template(), "nrv"), macros(world / "numbers.tex", "nrv")
    assert nrv and not nrv - generated.keys(), sorted(nrv - generated.keys())
    assert RUN_KEYS <= nrv  # the status paragraph's run facts
    fks = [_fk(f) for f in FAMILIES]
    assert {f"d19.{fk}.{k}" for fk in fks for k in D19_KEYS} <= nrv  # each family's D19 labels and their reasons
    assert {f"cost.{fk}.{k}" for fk in fks for k in COST_KEYS} <= nrv  # each family's cost, its S10 build time included
    assert {f"d19.{fk}.ambiguous.ids" for fk in fks} <= keys(_caveats_table(template()), "nrv")  # Tab. 6's new row
    assert generated["d19.np03.ambiguous.ids"] == "eval-alt-1, eval-nm-2" and generated["d19.np19.ambiguous.ids"] == "none"
    nat = keys(template(), "nat")
    assert nat and not nat - macros(PAPER / "generated" / "natural" / "numbers.tex", "nat").keys(), nat
    assert "s11.ids" not in nat  # the committed index's accepted families span both samples; run.families is the run's
    fresh = PAPER / "generated" / "fresh" / "numbers.tex"
    assert not keys(template(), "fv") - (macros(fresh, "fv").keys() if fresh.is_file() else set())


def _caveats_table(tex: str) -> str:
    """The template's hand-written table of per-family caveats (Tab. 6)."""
    start = tex.index("\\begin{table}")
    return tex[start:tex.index("\\end{table}", start)]


def test_every_cell_of_the_caveats_table_is_a_macro():
    """Tab. 6 is hand-written, and each of its family cells holds macros and their separators only."""
    body = _caveats_table(template())
    rows = body[body.index("\\midrule") + len("\\midrule"):body.index("\\bottomrule")].split("\\tabularnewline")
    rows = [r for r in rows if r.strip()]
    assert len(rows) == 6
    for row in rows:
        label, *cells = (re.sub(r"^\s*\\nrcaveat\{(.*)\}\s*$", r"\1", c, flags=re.DOTALL) for c in row.split("&"))
        assert len(cells) == len(FAMILIES), label
        for fam, cell in zip(FAMILIES, cells):
            fk = _fk(fam)
            assert re.findall(r"\\nrv\{[^}]*\}", cell) and all(fk in k for k in keys(cell, "nrv")), (label, fam)
            assert re.fullmatch(r"(?:\\nrv\{[^}]*\}|[\s();,]|of)*", cell), (label, cell)


# --------------------------------------------------------------------------- the premises


def test_the_synthetic_world_bears_out_the_template_s_premises(world):
    """The world carries the recorded construction facts, so the cells that measure them say what the sentences say."""
    assert not template_problems(macros(world / "numbers.tex", "nrv"))


def test_numbers_that_do_not_bear_out_a_premise_are_reported(world):
    numbers = macros(world / "numbers.tex", "nrv")
    changed = {**numbers, "b1.np04.norm": "yes", "il.np03.second": "graded", "run.invocations": "3",
               "run.revision": "e9c9c91, 1234abc", "audit.c2.np05.result": "passed"}
    del changed["refchecks.np05.rounds"]  # a status record that holds no integer fix_rounds
    problems = template_problems(changed)
    assert [p.split(":")[0] for p in problems] == ["refchecks.np05.rounds", "run.invocations", "b1.np04.norm",
                                                   "il.np03.second", "refchecks.np05.rounds", "audit.c2.np05.result",
                                                   "run.revision"]
    assert "the template states 'no' (D64, decision 3" in problems[2]
    assert template_problems({**numbers, "run.revision": mt.NOT_RECORDED}) == [
        "run.revision: the status paragraph names one code revision; the numbers hold 'not recorded'"]


@pytest.mark.skipif(not REAL_NUMBERS.is_file(), reason="natural-pr-v1 is not published yet (restructure plan, order of work 4)")
def test_the_run_s_own_numbers_bear_out_the_template_s_premises():
    """The integration check, on the run's own numbers before the family paragraphs are written: every key the template
    uses is generated and every premise holds; otherwise the sentences that state it are rewritten from the records."""
    assert not template_problems(macros(REAL_NUMBERS, "nrv"))


# --------------------------------------------------------------------------- (b) it compiles, with every number filled


def _preamble() -> str:
    main = (PAPER / "main.tex").read_text(encoding="utf-8")
    return main[:main.index("\\begin{document}")]


# Each marker main.tex prints also goes to the log, so that the test can find it there.
HOOKS = ("\\let\\tcunfilled\\unfilled\\renewcommand{\\unfilled}[1]{\\typeout{UNFILLED-MARKER: #1}\\tcunfilled{#1}}\n"
         "\\let\\tctodo\\todo\\renewcommand{\\todo}[1]{\\typeout{TODO-MARKER: #1}\\tctodo{#1}}\n")


def _pdflatex(build: Path, body: str) -> str:
    """Compile ``doc.tex`` (main.tex's preamble, the hooks and ``body``) in ``build`` twice, so that references resolve;
    return the log. Its console output is captured, never written to a file."""
    (build / "doc.tex").write_text(_preamble() + HOOKS + "\\begin{document}\n" + body + "\\end{document}\n", encoding="utf-8")
    shutil.copy2(PAPER / "references.bib", build / "references.bib")
    for _ in range(2):
        p = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"], cwd=build,
                           capture_output=True, text=True, errors="replace", timeout=600, check=False)
        log = (build / "doc.log").read_text(encoding="utf-8", errors="replace") if (build / "doc.log").exists() else ""
        assert p.returncode == 0, (p.stdout[-3000:], log[-3000:])
    return log


needs_pdflatex = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is not installed")


@needs_pdflatex
def test_the_template_compiles_with_main_tex_s_preamble_and_every_number_filled(world, tmp_path):
    build = tmp_path / "build"
    (build / "sections").mkdir(parents=True)
    shutil.copy2(TEMPLATE, build / "sections" / "natural.tex")
    shutil.copytree(world, build / "generated" / "natural_run")
    for sub in ("natural", "fresh"):
        src = PAPER / "generated" / sub / "numbers.tex"
        if src.is_file():
            (build / "generated" / sub).mkdir(parents=True)
            shutil.copy2(src, build / "generated" / sub / "numbers.tex")
    log = _pdflatex(build, "\\input{sections/natural}\n")
    assert not re.search(r"^! ", log, re.MULTILINE), log[-3000:]
    # The integration slot is the one marker: every number is filled, and no TODO is left.
    assert log.count("UNFILLED-MARKER") == 1 and "UNFILLED-MARKER: integration slot" in log and "TODO-MARKER" not in log
    # Every reference resolves: the template's own labels and its generated tables', none of another section.
    assert not re.findall(r"Reference `([^']+)' on page \d+ undefined", log)
    if shutil.which("pdftotext"):
        text = " ".join(subprocess.run(["pdftotext", "-layout", "doc.pdf", "-"], cwd=build, capture_output=True, text=True,
                                       check=True).stdout.split())
        assert text.count("UNFILLED") == 1 and f"[UNFILLED: {SLOT}]" in text, text[text.find("UNFILLED") - 20:][:200]
        assert "missing number" not in text and "TODO" not in text
        assert "eval-alt-1 (construction valid but checks fail), eval-nm-2 (construction invalid" in text  # as generated
        assert "make_tables.py --natural-run" in text and "\u2013natural-run" not in text  # two hyphens, no en dash


@needs_pdflatex
def test_main_tex_s_preamble_compiles_without_the_natural_run_s_numbers(tmp_path):
    """Until the natural run is published, generated/natural_run/numbers.tex does not exist: the preamble still compiles,
    and a key of it prints UNFILLED."""
    build = tmp_path / "bare"
    build.mkdir()
    log = _pdflatex(build, "\\nrv{run.date}\n")
    assert "UNFILLED-MARKER: missing number run.date" in log


def test_main_tex_defines_the_nrv_lookup_and_does_not_input_the_template_yet(world):
    main = (PAPER / "main.tex").read_text(encoding="utf-8")
    for p in ("fv", "nat", "nrv"):
        assert (f"\\newcommand{{\\{p}}}[1]{{\\ifcsname {p}:#1\\endcsname\\csname {p}:#1\\endcsname\\else"
                f"\\unfilled{{missing number #1}}\\fi}}") in main, p
    lookup = (world / "numbers.tex").read_text(encoding="utf-8").splitlines()[2]  # the lookup that numbers.tex names
    assert lookup.startswith("% \\newcommand{\\nrv}") and lookup.removeprefix("% ") in main
    assert "\\IfFileExists{generated/natural_run/numbers.tex}{\\input{generated/natural_run/numbers.tex}}{}" in main
    assert not re.search(r"\\input\{sections/natural(?:\.tex)?\}", main)  # the manuscript restructure places it


def test_the_template_s_one_unfilled_marker_is_the_integration_slot():
    """Outside the fallbacks of the generated tables' inputs, the template prints UNFILLED once on purpose: the closing
    paragraph's integration slot, which the posted PDF's check is to fail on until the integration replaces it."""
    tex = uncommented(template())
    fallbacks = re.findall(r"\\IfFileExists\{[^{}]*\}\{\\input\{[^{}]*\}\}\{\\unfilled\{", tex)
    assert tex.count("\\unfilled{") == len(fallbacks) + 1 == 3
    closing = tex[tex.index("\\paragraph{What the case studies can and cannot show.}"):]
    assert " ".join(closing.split()).startswith("\\paragraph{What the case studies can and cannot show.} "
                                                f"\\unfilled{{{SLOT}}}")


# --------------------------------------------------------------------------- (c) words, identifiers and numbers


def test_the_template_holds_no_word_the_plan_bans():
    flat = " ".join(template().split())  # comments included
    allowed = re.findall(HOW_OFTEN, flat, re.IGNORECASE)
    assert len(allowed) == 1  # the closing paragraph: what the case studies cannot show
    rest = re.sub(HOW_OFTEN, " ", flat, flags=re.IGNORECASE)
    for pat in (*BANNED, r"\bhow\s+often\b"):
        assert not re.search(pat, rest, re.IGNORECASE), (pat, re.search(pat, rest, re.IGNORECASE).group(0))


def test_the_template_names_no_model_agent_tool_tier_or_product():
    tex = template()
    record = json.loads((ROOT / mt.NATURAL_INPUTS["M0"]).read_text())
    mt._check_private(tex, "paper/sections/natural.tex", digit_runs=True, names=mt._agent_names(record))
    for pat in TIER:
        assert not re.search(pat, tex, re.IGNORECASE), pat
    assert re.search(r"\bconfiguration-A\b", tex)  # configurations are named by letter (A, B) only


def test_every_number_of_the_template_is_a_macro():
    text = uncommented(template())
    for pat in IDENTIFIERS:
        text = re.sub(pat, " ", text)
    assert not re.findall(r".{0,30}\d.{0,30}", text), re.findall(r".{0,30}\d.{0,30}", text)
    words = re.findall(NUMBER_WORDS, uncommented(template()).replace("one model family of one provider", " "), re.IGNORECASE)
    assert not words, words


def test_no_option_prints_as_an_en_dash():
    """With main.tex's T1 fonts a double hyphen is set as an en dash, in \\texttt too: an option is written -{}- (as in
    make_tables.py -{}-natural-run), and the text uses no double hyphen."""
    assert "--" not in uncommented(template())
    assert "make\\_tables.py\n-{}-natural-run" in template() or "make\\_tables.py -{}-natural-run" in template()


# --------------------------------------------------------------------------- its records


def test_every_decision_log_entry_the_template_cites_is_logged_or_the_next_one():
    """Each entry the template cites is a heading of docs/decision_log.md, but the pending entries its header declares
    (``% * Pending decision-log entry D<n>: ...``), which must be the log's next numbers: once one is logged, or another
    entry takes its number first, this fails until the template and its header agree with the log again."""
    log = (ROOT / "docs" / "decision_log.md").read_text(encoding="utf-8")
    logged = {int(n) for n in re.findall(r"^### D(\d+)\. ", log, re.MULTILINE)}
    tex = template()
    pending = {int(n) for n in re.findall(r"^% \* Pending decision-log entry D(\d+)\b", tex, re.MULTILINE)}
    cited = {int(n) for n in re.findall(r"\bD(\d+)\b", uncommented(tex))}
    assert cited - logged == pending, (sorted(cited - logged), sorted(pending))
    assert sorted(pending) == list(range(max(logged) + 1, max(logged) + 1 + len(pending))), (sorted(pending), max(logged))


def paragraphs(tex: str) -> dict[str, str]:
    """The template's paragraphs by their titles (``\\paragraph{...}``), each to the next one, with comments left out and
    whitespace collapsed."""
    parts = re.split(r"\\paragraph\{([^}]*)\}", uncommented(tex))
    return {title: " ".join(body.split()) for title, body in zip(parts[1::2], parts[2::2])}


# The disclosures that the records require of the template, each in its paragraph (its text with comments left out and
# whitespace collapsed), with the entries it cites: the reviews of the template against decision log D19, D33, D59, D63
# to D76 and protocol §2, §15.6, §16.4, §18.2, §19.6 and §20.
DISCLOSURES = {
    "Status.": (
        "accepted families of the first sample (\\nrv{run.families})",  # the run's own, not both samples' (D76)
        "D76 records why the first invocation was stopped",  # whatever the manifest's count of invocations
        "Protocol v0.12 (protocol~\\S20) gave each sample a run of its own",
        ("When this run started, the extension's run, \\texttt{natural-pr-v2}, had not been made: the extension's S10 "
         "step was stopped at a usage limit, and the task directories it left are to be built again from the start "
         "(D66, D75)"),
    ),
    "What was built.": (
        ("the source-evidence label of the pre-review states, the label of the first estimand of protocol~\\S15.6 "
         "(D64, decision~14)"),
    ),
    "Caveats.": (
        ("These hold for every number of this section and of its tables, whose captions point here with the marker "
         "$^{\\ddagger}$."),
        ("which rests on the reviewer's request, the addressing commit and the agreement of the model judges of S9 "
         "(protocol~\\S15.6)"),
        "the second labeling leaves them out (D72, D75, D76)",
        ("as the run's first step, once building had stopped for the first sample: a builder reading of "
         "protocol~\\S19.7 and \\S20.2, pending the owner's review (D73, D74, D76)"),
        "and so did some host coordinators, which write no generated content (D65, D72)",
        "a search of each exposed generator run's text and tool inputs",
        "The templates whose sources carry an owner-context line leave it out",
        ("The runs of P1 and of P5 carried, in their first message, a harness entry relaying the owner's latest "
         "message"),
        ("It could still nudge an agent toward less or more work. The decision log records which runs carried it, and "
         "nothing was regenerated for it, a builder decision pending the owner's review (D67, D68, D77)."),
        ("The agent tool offers no per-call tool restriction, so each natural agent had its agent type's tools, as the "
         "controlled agents of the same source workflows had, and the natural-agent audit read every network use and "
         "tool call (D64, ``Agents'' and decision~11; D65)."),
        ("An environment block naming the study repository as the working directory was in every natural agent's "
         "context, as in the fresh attempts (D65; protocol~\\S18.2)."),
        ("with no pooled rate, interval or p-value (protocol~\\S19.6, \\S20.3). Nor do we give a total over the "
         "families, or pool anything with the controlled arm (protocol~\\S2)."),
    ),
    "NP-03.": (
        ("No near-miss writer ran the repository's tests, the writer of eval-nm-3 included, which started the task "
         "image itself, as the family's audit records of P7 say (D75, D77)."),
        "The review of the reference checks was ok, with coverage remarks on R2 and R5, so no fix round ran (D33, D72).",
    ),
    "NP-04.": (
        ("rejecting the development alternative, which, by the revisers' account, cannot be told apart from the "
         "reference on the requirement it targets (D70)."),
        "the audit of P7 and the strict re-audit missed a call it made (D75).",
    ),
    "NP-05.": (
        "Its reference checks were frozen after \\nrv{refchecks.np05.rounds} fix rounds",
        "The writer of eval-nm-3 remarks that a strict reader could also count it against R8; D19 decides its label (D75).",
    ),
    "NP-18.": ("The review of the reference checks was ok, with a coverage remark on R4, so no fix round ran (D33, D72).",),
    "NP-19.": (("The second review of the reference checks, after their fix round, was ok, with a coverage remark on R1, so "
                "no further fix round ran (D33, D75)."),),
    "NP-20.": ("The review of the reference checks was ok, with a coverage remark on R11, so no fix round ran (D33, D72).",),
    "What the case studies can and cannot show.": (
        ("S10 passed \\nat{s10.first.passed} of the \\nat{s10.first.processed} families of the first sample that it "
         "processed (D59)"),
        ("This cost leaves out what no such record holds, as the run's analysis lists it: the host's own steps, which "
         "the host coordinators run (D65), apart from the run's grading; agent runs that leave no generation record, "
         "the mappers among them; stages S1 to S9"),
        "So it is not the whole cost of building a family: D68 reports the host coordinators' share of a phase.",
    ),
}
# What the template must not say (the same reviews): each with why.
NOT_SAID = (
    (r"\\nat\{s11\.ids\}", "the committed index's accepted families span both samples"),
    (r"S10 accepted", "S10 passes a family, S11 accepts it (protocol §16.4; D59)"),
    (r"primary for the pre-review", "protocol §15.6 does not call the source-evidence label primary"),
    (r"stated here alone", "the generated captions restate some caveats"),
    (r"both families", "a quantifier over families"),
    (r"its families' S10 step", "D66 and D75 say it of the task directories the stopped step left"),
    (r"alternative's construction label", "D70 says it of an attack, not of NP-04's alternative"),
    (r"The templates leave out", "D64 (i) concerns the templates whose sources carry the line"),
    (r"No total over the families is given \(protocol", "protocol §19.6 names no total"),
    (r"has not been made", "a status statement without its date"),
)


def test_the_template_carries_the_disclosures_its_records_require():
    """Each disclosure of :data:`DISCLOSURES` is in its paragraph, and nothing of :data:`NOT_SAID` is anywhere: the
    template's statements as the records word them (the reviews' findings), so that an edit that drops one fails."""
    pars = paragraphs(template())
    assert list(pars) == ["Status.", "What was built.", "Caveats.", "Reading the tables and the family paragraphs.",
                          *(f"{f}." for f in FAMILIES), "What the case studies can and cannot show."]
    for title, said in DISCLOSURES.items():
        for text in said:
            assert text in pars[title], (title, text)
    flat = " ".join(uncommented(template()).split())
    for pat, why in NOT_SAID:
        assert not re.search(pat, flat), (pat, why)


# The terms that a cell of Tab. 6 can hold in place of a value, as make_tables.py --natural-run writes them.
CAVEAT_TERMS = ("not recorded", "unrecognised status", "not known", "left out", "not graded", "none")


def _caveat_cells(numbers: dict[str, str]) -> list[str]:
    """Tab. 6's family cells as they print with ``numbers`` (a key that is not generated prints MISSING)."""
    body = _caveats_table(template())
    rows = body[body.index("\\midrule") + len("\\midrule"):body.index("\\bottomrule")].split("\\tabularnewline")
    return [re.sub(r"\\nrv\{([^}]*)\}", lambda m: numbers.get(m.group(1), "MISSING"), cell)
            for row in rows if row.strip() for cell in row.split("&")[1:]]


def test_every_term_a_cell_of_the_caveats_table_can_hold_is_defined_in_its_caption(run, tmp_path):
    """As the generated tables define the terms their cells use in their captions, so does Tab. 6, for every term its
    keys can hold: a missing or unrecognised status record, a labeler without a status, no regression-norm overlay, a
    family the second labeling leaves out or that the run did not grade with the labeler, and no ambiguous candidate."""
    copy = tmp_path / "run" / run.name
    shutil.copytree(run, copy)
    a = json.loads((copy / "analysis.json").read_text(encoding="utf-8"))
    fams = a["natural"]["families"]
    fams["NP-03"]["construction"]["reference_checks"] = {"recorded": False, "status": None, "usable": None, "fix_rounds": None}
    fams["NP-04"]["construction"]["reference_checks"] = {"recorded": True, "status": None, "usable": None, "fix_rounds": 0}
    fams["NP-05"]["labeler"]["status"] = None
    fams["NP-18"]["b1_equals_regression_norm"] = {"equal": None, "why": "synthetic"}
    a["independent_labeling"]["tasks"] = [t for t in a["independent_labeling"]["tasks"] if t != "NP-20"]
    (copy / "analysis.json").write_text(json.dumps(a), encoding="utf-8")
    cells = _caveat_cells(macros(_generate(copy, tmp_path / "paper") / "numbers.tex", "nrv"))
    used = {term for c in cells for term in CAVEAT_TERMS if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", c)}
    assert used == set(CAVEAT_TERMS), set(CAVEAT_TERMS) - used
    caption = re.search(r"\\caption\{(.*?)\}\\label\{tab:nr-caveats\}", _caveats_table(template()), re.DOTALL).group(1)
    caption = " ".join(caption.split())
    for term in used:
        assert f"{term}:" in caption, term
    assert caption.endswith("$^{\\ddagger}$Natural case study; caveats in Section~\\ref{sec:natural-cases}.")
