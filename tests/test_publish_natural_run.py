"""``scripts/publish_natural_run.py`` (build plan WP-H; protocol §17.4, decision log D47): exactly four files are
published, ``results_public.jsonl`` holds no private field, the run and the publication directory are refused outside
``data/natural/runs`` and ``results/runs``, the checks fail closed when the run's tasks cannot be read, and a text that
holds natural material is reported by location and not published. Also ``scripts/compare_runs.py`` on natural runs.

A scratch repository root holds a synthetic natural task (tests/natural_task_layout.py), a synthetic finished run of
it and synthetic screening texts with the manifest that samples them. The planted login is a synthetic one. Not research
evidence.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from natural_task_layout import B1_CHECKS, COMMENT_TEXT, REPLY_TEXT, build_natural_task

from tracecontract import natural_privacy as npv

ROOT = Path(__file__).resolve().parents[1]
RUN = "natural-fx-1"
LOGIN = "fx-natural-reviewer"  # a synthetic login, given to the check as an AIDev login
UPSTREAM_LINE = "assert add(None, 2) == 2 and add(2, None) == 2"  # a line of the reference patch and of B1's overlay
BASE_LINE = "    return fx_render_gallery(widget_cache, zoom_level=zoom)"  # a line of the base snapshot only
SCREENED = ("The retry loop in the uploader swallows the timeout error, so the job reports success while nothing was "
            "stored; please surface the error to the caller instead.")  # a sampled comment that was never built
# NP-95's review comment and reply, in the shapes of two accepted families' correction comments (synthetic): 21
# characters and 3 words, 37 characters and 5 words. NP-95 lies under the tasks root but is not in the run.
SHORT_21 = "Don't mutate defaults"
SHORT_37 = 'Swap "thumbnails" for naïve previews.'


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pub = _load("publish_natural_run")
scan = pub.scan_module()


def _result(verifier: str, candidate: str, outcome: str, statuses: list[str]) -> str:
    checks = [{"check_id": B1_CHECKS[i % len(B1_CHECKS)], "status": s, "duration_s": 0.01,
               "message": f"E   {UPSTREAM_LINE}" if s != "passed" else ""} for i, s in enumerate(statuses)]
    r = {"schema_version": "0.1.0", "run_id": RUN, "task_id": "NP-90", "verifier_id": verifier, "candidate_id": candidate,
         "outcome": outcome, "reward": 1.0 if outcome == "pass" else 0.0, "checks": checks,
         "diagnostics": [f"repo_tests: {UPSTREAM_LINE}"], "started_at": "2026-11-21T10:00:00+00:00",
         "finished_at": "2026-11-21T10:00:05+00:00", "wall_s": 5.25, "harness_version": "tc-harness/0.3.5",
         "log_sha256": "ab" * 32}
    return json.dumps(r, separators=(",", ":"))


def _manifest(tasks: list | None = None) -> dict:
    return {"run_id": RUN, "started_at": "2026-11-21T10:00:00+00:00", "finished_at": "2026-11-21T11:00:00+00:00",
            "repeats": 3, "tasks": tasks if tasks is not None else [
                {"task_id": "NP-90", "task_dir": "data/natural/tasks/NP-90",
                 "verifiers": {"repo_tests": {"condition": "repo_tests", "n_checks": 2, "version": 1}},
                 "candidates": {"NP-90-pre-review": {"origin": "natural_pre_review"}}}]}


def _texts(repo: Path) -> Path:
    return repo / "screening" / "texts.jsonl"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    """A scratch repository root with NP-90, the finished run data/natural/runs/natural-fx-1 and the screening texts of
    one sampled comment that was never built (:func:`_texts`), which the screening manifest samples."""
    build_natural_task(tmp_path, index=False)
    _texts(tmp_path).parent.mkdir()
    _texts(tmp_path).write_text(json.dumps({"comment_id": 501, "comment_body": SCREENED, "issue_title": "",
                                            "issue_body": "", "pr_title": "", "diff_hunk": ""}) + "\n")
    manifest = tmp_path / "screening" / "s9.json"
    manifest.write_text(json.dumps({"sample": {"rows": [{"comment_id": 501}]}}))
    monkeypatch.setattr(scan, "SCREENING_MANIFESTS", (manifest,))  # the manifests whose comments the texts must hold
    (tmp_path / "data" / "natural" / "snapshots" / "NP-90" / "fxnat" / "render.py").write_text(
        f"def render(widget_cache, zoom):\n{BASE_LINE}\n", encoding="utf-8")
    run = tmp_path / "data" / "natural" / "runs" / RUN
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps(_manifest(), indent=2) + "\n", encoding="utf-8")
    lines = [_result("repo_tests", "NP-90-reference", "pass", ["passed", "passed"]),
             _result("repo_tests", "NP-90-pre-review", "task_failure", ["passed", "failed"]),
             _result("initial_plain", "NP-90-pre-review", "verifier_error", ["error", "missing", "skipped"])]
    (run / "results.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run / "analysis.json").write_text(json.dumps({"n_tasks": 1, "n_families": 1, "mode": "case study"}, indent=2) + "\n")
    (run / "analysis.md").write_text("# Analysis of natural-fx-1\n\nOne natural family, reported as a case study.\n")
    (run / "logs").mkdir()
    (run / "report.html").write_text("<p>private report</p>")
    (tmp_path / "results" / "runs").mkdir(parents=True)
    np95 = tmp_path / "data" / "natural" / "tasks" / "NP-95"
    np95.mkdir()
    (np95 / "session.json").write_text(json.dumps({"session_id": "s95", "events": [
        {"event_id": f"s95/{e}", "author": "human", "text": t} for e, t in (("review/1", SHORT_21), ("reply/1", SHORT_37))]},
        ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _publish(repo: Path, run: str = RUN, out: str | None = None, **kw) -> int:
    kw.setdefault("screening", [_texts(repo)])
    return pub.publish(repo / "data" / "natural" / "runs" / run, repo / "results" / "runs" / (out or run),
                       logins=scan.login_patterns([LOGIN]), repo=repo, scan=scan, **kw)


def _set_manifest(repo: Path, manifest: dict) -> None:
    (repo / "data" / "natural" / "runs" / RUN / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_exactly_the_four_files_and_no_private_field(repo, capsys):
    assert _publish(repo) == 0
    dest, run = repo / "results" / "runs" / RUN, repo / "data" / "natural" / "runs" / RUN
    assert sorted(p.name for p in dest.iterdir()) == ["analysis.json", "analysis.md", "manifest.json", "results_public.jsonl"]
    for name in ("manifest.json", "analysis.json", "analysis.md"):
        assert (dest / name).read_bytes() == (run / name).read_bytes()
    private = (run / "results.jsonl").read_text().splitlines()
    public = (dest / "results_public.jsonl").read_text()
    rows = [json.loads(x) for x in public.splitlines()]
    assert len(rows) == len(private) == 3
    for row, line in zip(rows, private, strict=True):
        assert tuple(row) == pub.PUBLIC_FIELDS
        assert row["private_line_sha256"] == hashlib.sha256(line.encode()).hexdigest()
        assert set(row["check_counts"]) == set(pub.CHECK_STATUSES)
    assert rows[1]["check_counts"] == {"passed": 1, "failed": 1, "error": 0, "skipped": 0, "missing": 0}
    assert rows[2]["check_counts"] == {"passed": 0, "failed": 0, "error": 1, "skipped": 1, "missing": 1}
    assert (rows[1]["outcome"], rows[1]["reward"], rows[1]["harness_version"]) == ("task_failure", 0.0, "tc-harness/0.3.5")
    for private_bit in (*B1_CHECKS, "test_mod.py", "add(None", "checks", "diagnostics", "message", "wall_s", "started_at"):
        assert private_bit not in public, private_bit
    assert "published natural-fx-1 to results/runs/natural-fx-1" in capsys.readouterr().out
    assert _publish(repo) == 0  # publishing again replaces the four files


@pytest.mark.parametrize("run, out, why", [
    (RUN, "../natural-fx-1", "results/runs/<run>"),  # beside results/runs
    (RUN, "natural-other", "results/runs/<run>"),  # another name than the run's
    (RUN, f"{RUN}/sub", "results/runs/<run>"),  # nested deeper
    ("../../../results/runs/natural-fx-0", "natural-fx-0", "data/natural/runs/<run>"),  # a run outside data/natural/runs
    ("../natural-fx-1", RUN, "data/natural/runs/<run>"),  # beside data/natural/runs
    ("pr-v1", "pr-v1", "natural-"),  # a name the .gitignore rules do not cover
])
def test_refused_locations(repo, run, out, why):
    (repo / "results" / "runs" / "natural-fx-0").mkdir()
    (repo / "data" / "natural" / "runs" / "pr-v1").mkdir()
    before = sorted(str(p.relative_to(repo)) for p in (repo / "results").rglob("*"))
    with pytest.raises(pub.Refused, match=why.replace("<", r"\<").replace(">", r"\>")):
        _publish(repo, run, out)
    assert sorted(str(p.relative_to(repo)) for p in (repo / "results").rglob("*")) == before


def test_refused_runs_and_publication_directories(repo):
    run = repo / "data" / "natural" / "runs" / RUN
    dest = repo / "results" / "runs" / RUN
    manifest = json.loads((run / "manifest.json").read_text())
    (run / "manifest.json").write_text(json.dumps({**manifest, "finished_at": None}))
    with pytest.raises(pub.Refused, match="finished_at"):
        _publish(repo)
    (run / "manifest.json").write_text(json.dumps(manifest))
    (run / "analysis.md").rename(run / "analysis.md.bak")
    with pytest.raises(pub.Refused, match="analysis.md"):
        _publish(repo)
    (run / "analysis.md.bak").rename(run / "analysis.md")
    dest.mkdir()
    (dest / "results.jsonl").write_text("{}\n")  # a private file beside the published ones
    with pytest.raises(pub.Refused, match="results.jsonl"):
        _publish(repo)
    assert sorted(p.name for p in dest.iterdir()) == ["results.jsonl"]


def test_the_checks_fail_closed_when_the_runs_tasks_cannot_be_read(repo):
    """A run whose tasks' material cannot be read is refused, never checked against nothing: a task directory that
    does not exist, one outside the tasks root, a manifest without tasks, a task that is not natural, a task without its
    base snapshot. Its outputs (here B1's check id and an upstream line) are not published."""
    (repo / "data" / "natural" / "runs" / RUN / "analysis.json").write_text(
        json.dumps({"b1": B1_CHECKS[1], "line": UPSTREAM_LINE}))
    task = _manifest()["tasks"][0]
    shutil.copytree(repo / "data" / "natural" / "tasks" / "NP-90", repo / "data" / "natural" / "tasks_copy" / "NP-90")
    cases = [([{**task, "task_dir": "data/natural/tasks_old/NP-90"}], "not a task directory under data/natural/tasks"),
             ([{**task, "task_dir": "data/natural/tasks_copy/NP-90"}], "not a task directory under data/natural/tasks"),
             ([], "lists no task"),
             ([{**task, "task_id": "NP-93", "task_dir": None}], "NP-93")]
    for tasks, why in cases:
        _set_manifest(repo, _manifest(tasks))
        with pytest.raises(pub.Refused, match=why):
            _publish(repo)
        assert not (repo / "results" / "runs" / RUN).exists()
    (repo / "data" / "natural" / "tasks" / "NP-94").mkdir()
    (repo / "data" / "natural" / "tasks" / "NP-94" / "task.json").write_text(json.dumps({"population": "controlled"}))
    _set_manifest(repo, _manifest([{**task, "task_id": "NP-94", "task_dir": "data/natural/tasks/NP-94"}]))
    with pytest.raises(pub.Refused, match="no code line or check id"):  # read, but it holds no code to check against
        _publish(repo)
    _set_manifest(repo, _manifest())
    snapshot = repo / "data" / "natural" / "snapshots" / "NP-90"
    kept = repo / "kept-snapshot"
    shutil.copytree(snapshot, kept)
    for f in snapshot.rglob("*.py"):  # a base snapshot without a code line: the base-code check could not run
        f.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(pub.Refused, match="no code line could be read from its base snapshot"):
        _publish(repo)
    shutil.rmtree(snapshot)
    with pytest.raises(pub.Refused, match="no base snapshot"):
        _publish(repo)
    shutil.copytree(kept, snapshot)
    # The run's task locates its base snapshot elsewhere (its provenance notes) than the one read with the tasks.
    prov = repo / "data" / "natural" / "tasks" / "NP-90" / "provenance.json"
    good = prov.read_text(encoding="utf-8")
    record = json.loads(good)
    record["notes"] = json.dumps({**json.loads(record["notes"]), "snapshot_root": "data/natural/snapshots_b"})
    prov.write_text(json.dumps(record), encoding="utf-8")
    shutil.copytree(kept, repo / "data" / "natural" / "snapshots_b" / "NP-90")
    with pytest.raises(pub.Refused, match="is not the one read with the natural tasks"):
        _publish(repo)
    prov.write_text(good, encoding="utf-8")
    (repo / "data" / "natural" / "tasks" / "NP-95" / "session.json").write_text('{"events": [', encoding="utf-8")
    with pytest.raises(pub.Refused, match="--natural-texts: .*cannot be read as JSON"):  # a task file of another task
        _publish(repo)
    assert not (repo / "results" / "runs" / RUN).exists()


def test_an_empty_login_list_is_refused(repo):
    """The login check fails closed: with no AIDev login to check against (the AIDev files gave none), nothing is
    published."""
    with pytest.raises(pub.Refused, match="no AIDev login"):
        pub.publish(repo / "data" / "natural" / "runs" / RUN, repo / "results" / "runs" / RUN, logins=[], repo=repo,
                    scan=scan, screening=[_texts(repo)])
    assert not (repo / "results" / "runs" / RUN).exists()


def test_a_relative_tasks_root_is_read_from_the_repository(repo, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    _set_manifest(repo, _manifest([{**_manifest()["tasks"][0], "task_dir": None}]))  # graded from outside the repository
    assert _publish(repo, tasks_root="data/natural/tasks") == 0
    (repo / "data" / "natural" / "runs" / RUN / "analysis.md").write_text(f"# x\n\n{B1_CHECKS[0]}\n")
    assert _publish(repo, tasks_root="data/natural/tasks") == 1  # the task's check ids were read from the repository's root


@pytest.mark.parametrize("name, planted, kind", [
    ("analysis.md", f"# Analysis\n\nnotes\nThe comment: {COMMENT_TEXT}\n", "4: natural text window (NP-90)"),
    ("analysis.md", f'# Analysis\n\nThe reviewer replied: "{REPLY_TEXT}"\n', "3: natural short text (NP-90)"),
    ("analysis.md", f"# Analysis\n\nthanks to {LOGIN}\n", "3: aidev login #0"),
    ("analysis.md", "# Analysis\n\ncc @fx-someone\n", "3: @handle"),
    ("analysis.json", json.dumps({"b1": [B1_CHECKS[1]]}, indent=1), "3: check id of a natural task (NP-90)"),
    ("analysis.json", json.dumps({"x": UPSTREAM_LINE}), "1: code line of a natural task (NP-90)"),
    ("analysis.md", f"# Analysis\n\n{BASE_LINE}\n", "3: code line of a natural task's base snapshot (NP-90)"),
    ("manifest.json", json.dumps({"finished_at": "x", "tasks": [_manifest()["tasks"][0]],
                                  "repo": "https://github.com/{owner}/fxnat"}), "1: natural repository name (NP-90)"),
    # The shapes of two accepted families' correction comments: 21 characters and 3 words, 37 and 5; also escaped.
    ("analysis.md", f"# Analysis\n\nThe review comment: {SHORT_21}\n", "3: natural short text (NP-95)"),
    ("analysis.md", f"# Analysis\n\n<p>{html.escape(SHORT_21)}</p>\n", "3: natural short text (NP-95)"),
    ("analysis.json", json.dumps({"reply": SHORT_37}), "1: natural short text (NP-95)"),
    ("analysis.md", f"# Analysis\n\n> {html.escape(SHORT_37.upper())}\n", "3: natural short text (NP-95)"),
])
def test_natural_material_is_reported_by_location_and_not_published(repo, capsys, name, planted, kind):
    (repo / "data" / "natural" / "runs" / RUN / name).write_text(planted, encoding="utf-8")
    assert _publish(repo) >= 1
    out = capsys.readouterr().out
    assert f"results/runs/{RUN}/{name}:{kind}" in out and "nothing written" in out
    assert not (repo / "results" / "runs" / RUN).exists()
    for secret in (LOGIN, "fx-someone", "fxnat", B1_CHECKS[1], UPSTREAM_LINE, BASE_LINE.strip(), COMMENT_TEXT[5:30],
                   REPLY_TEXT[:20], SHORT_21, "mutate defaults", "thumbnails"):
        assert secret not in out


def test_screening_texts_are_required_and_checked(repo, capsys):
    """A sampled comment that was never built is known only from the screening texts, so the publisher refuses to run
    without them (fail closed), and with them reports its text."""
    (repo / "data" / "natural" / "runs" / RUN / "analysis.md").write_text(f"# x\n\nA comment said: {SCREENED}\n")
    with pytest.raises(pub.Refused, match="no screening texts"):
        _publish(repo, screening=[])
    _texts(repo).with_name("short.jsonl").write_text(_texts(repo).read_text().replace("501", "502"))
    with pytest.raises(pub.Refused, match="lack 1 sampled comment"):  # texts that lack a sampled comment
        _publish(repo, screening=[_texts(repo).with_name("short.jsonl")])
    assert not (repo / "results" / "runs" / RUN).exists()
    assert _publish(repo) == 1
    assert f"results/runs/{RUN}/analysis.md:3: natural text window (screened comment 501)" in capsys.readouterr().out
    assert not (repo / "results" / "runs" / RUN).exists()


def test_a_line_of_a_large_base_file_is_not_published(repo, capsys):
    """A base snapshot's Python file over 1 MB is read like any other: a line of it in the run's analysis is reported."""
    tail = "    return fx_large_lookup(table_cache, entry_index=key)"
    filler = "".join(f"TABLE_{i:06d} = compute_entry({i}, scale=FACTOR)\n" for i in range(24000))
    (repo / "data" / "natural" / "snapshots" / "NP-90" / "fxnat" / "tables.py").write_text(filler + tail + "\n")
    (repo / "data" / "natural" / "runs" / RUN / "analysis.md").write_text(f"# x\n\n{tail}\n")
    assert _publish(repo) == 1
    assert f"results/runs/{RUN}/analysis.md:3: code line of a natural task's base snapshot (NP-90)" in capsys.readouterr().out
    assert not (repo / "results" / "runs" / RUN).exists()


def test_every_base_line_is_checked_before_publication(repo, capsys):
    """The publisher looks for every line of the base snapshots but the idioms, also one of common words that the scan
    leaves out (natural_privacy.distinctive_line): a natural run's outputs are few and are published once."""
    common = "    except (TypeError, KeyError, ValueError):"
    (repo / "data" / "natural" / "snapshots" / "NP-90" / "fxnat" / "errors.py").write_text(
        f"def guard():\n    try:\n        pass\n{common}\n        pass\n")
    (repo / "data" / "natural" / "runs" / RUN / "analysis.md").write_text(f"# x\n\n{common}\n")
    generic = scan.pre_natural_lines()
    if generic is not None:  # with the pre-natural corpus, the scan would not look for this line
        assert common.strip() not in generic and not npv.distinctive_line(common, npv._line_counts(generic))
    assert _publish(repo) == 1
    assert f"results/runs/{RUN}/analysis.md:3: code line of a natural task's base snapshot (NP-90)" in capsys.readouterr().out


def test_compare_runs_on_natural_runs_gives_outcomes_and_rewards_only(repo, capsys):
    """scripts/compare_runs.py on two natural runs, and on a published one: no diagnostics, check ids or messages."""
    cr = _load("compare_runs")
    assert _publish(repo) == 0
    runs = repo / "data" / "natural" / "runs"
    old, new = runs / RUN, runs / "natural-fx-2"
    new.mkdir()
    (new / "manifest.json").write_bytes((old / "manifest.json").read_bytes())
    lines = (old / "results.jsonl").read_text().splitlines()
    flipped = json.loads(lines[0]) | {"outcome": "task_failure", "reward": 0.0}  # a discordant pair
    (new / "results.jsonl").write_text("\n".join([json.dumps(flipped), *lines[1:]]) + "\n")
    for a, b in ((old, new), (repo / "results" / "runs" / RUN, new)):  # private vs private, published vs private
        assert cr.is_natural(a) and cr.is_natural(b)
        cr.main(str(a), str(b))
        out = capsys.readouterr().out
        written = (b / f"compare_{a.name}.json").read_text() + (b / f"compare_{a.name}.md").read_text()
        summary = json.loads((b / f"compare_{a.name}.json").read_text())
        assert summary["pairs_in_both"] == 3 and len(summary["reward_discordant"]) == 1
        assert summary["reward_discordant"][0] == {"verifier_id": "repo_tests", "candidate_id": "NP-90-reference", "old": "pass",
                                                   "new": "task_failure", "old_reward": 1.0, "new_reward": 0.0}
        for private_bit in (*B1_CHECKS, UPSTREAM_LINE, "tc-harness", "5.2 s"):
            assert private_bit not in written and private_bit not in out, private_bit
        rows = summary["reward_discordant"] + summary["outcome_discordant"] + summary["changed_verifier_pairs"]
        assert not any(k.endswith(("diagnostics", "harness", "wall_s")) for r in rows for k in r)
        assert "Diagnostics" not in written and "natural" in summary
    assert not cr.is_natural(ROOT / "results" / "runs" / "pilot-v0.3.3")


def test_compare_runs_detects_every_natural_run(tmp_path, monkeypatch):
    """Each sign of a natural run, on its own: where it lies, its name or run id, a natural pre-review candidate, a
    natural population (natural, natural:chat, natural:pr-review) at its task_dir, and for a task graded from outside the
    repository (task_dir null) the task of that id under data/natural/tasks."""
    cr = _load("compare_runs")
    monkeypatch.setattr(cr, "REPO", tmp_path)
    monkeypatch.setattr(cr, "NATURAL_RUNS", tmp_path / "data" / "natural" / "runs")

    def task(rel: str, population: str) -> None:
        (tmp_path / rel).mkdir(parents=True)
        (tmp_path / rel / "task.json").write_text(json.dumps({"task_id": Path(rel).name, "population": population}))

    def run(name: str, tasks: list, run_id: str | None = None, under: str = "results/runs") -> Path:
        d = tmp_path / under / name
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"run_id": run_id or name, "tasks": tasks}))
        return d

    task("tasks/CS-01", "controlled")
    controlled = [{"task_id": "CS-01", "task_dir": "tasks/CS-01", "candidates": {"CS-01-alt": {"origin": "valid_alternative"}}}]
    assert not cr.is_natural(run("pilot-x", controlled))
    assert cr.is_natural(run("natural-pr-v1", controlled))
    assert cr.is_natural(run("rerun-7", controlled, run_id="natural-pr-v1"))
    assert cr.is_natural(run("r-under", controlled, under="data/natural/runs"))
    outside = [{"task_id": "NP-03", "task_dir": None, "candidates": {"NP-03-pre-review": {"origin": "natural_pre_review"}}}]
    assert cr.is_natural(run("r-outside", outside))
    for i, population in enumerate(("natural", "natural:chat", "natural:pr-review")):
        task(f"ext/T-{i}", population)
        assert cr.is_natural(run(f"r-pop-{i}", [{"task_id": f"T-{i}", "task_dir": f"ext/T-{i}", "candidates": {}}])), population
    task("data/natural/tasks/NP-50", "natural:pr-review")
    assert cr.is_natural(run("r-null", [{"task_id": "NP-50", "task_dir": None, "candidates": {}}]))
    assert not cr.is_natural(run("r-null-cs", [{"task_id": "CS-01", "task_dir": None, "candidates": {}}]))


def test_compare_runs_reduces_a_natural_run_graded_from_outside_the_repository(tmp_path, monkeypatch):
    """A natural run outside data/natural/runs whose manifest records no task_dir: no diagnostics in the comparison."""
    cr = _load("compare_runs")
    monkeypatch.setattr(cr, "REPO", tmp_path)
    monkeypatch.setattr(cr, "NATURAL_RUNS", tmp_path / "data" / "natural" / "runs")
    task = {"task_id": "NP-90", "task_dir": None, "verifiers": {"repo_tests": {"version": 1, "content_sha256": "c"}},
            "candidates": {"NP-90-pre-review": {"origin": "natural_pre_review"}}}
    dirs = []
    for name, outcome in (("old-run", "pass"), ("new-run", "task_failure")):
        d = tmp_path / "results" / "runs" / name
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"run_id": name, "tasks": [task]}))
        r = json.loads(_result("repo_tests", "NP-90-pre-review", outcome, ["failed"]))
        (d / "results.jsonl").write_text(json.dumps(r) + "\n")
        dirs.append(d)
    cr.main(str(dirs[0]), str(dirs[1]))
    written = (dirs[1] / "compare_old-run.json").read_text() + (dirs[1] / "compare_old-run.md").read_text()
    assert UPSTREAM_LINE not in written and B1_CHECKS[0] not in written and "natural" in json.loads(
        (dirs[1] / "compare_old-run.json").read_text())


def test_cli_refuses_before_reading_the_aidev_files(tmp_path, capsys):
    code = pub.main([str(tmp_path / RUN), "--out", str(ROOT / "results" / "runs" / RUN),
                     "--aidev-logins", str(tmp_path / "no-aidev-files-here"), "--screening-texts", str(tmp_path / "t.jsonl")])
    assert code == 2 and "refused" in capsys.readouterr().err
    assert not (ROOT / "results" / "runs" / RUN).exists()
    with pytest.raises(SystemExit):  # the screening texts are required
        pub.main([str(tmp_path / RUN), "--out", str(ROOT / "results" / "runs" / RUN), "--aidev-logins", str(tmp_path)])
    assert "--screening-texts" in capsys.readouterr().err
