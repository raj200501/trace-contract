"""Licences, download records and data card of the natural PR-review arm (THIRD_PARTY_LICENSES/README.md,
docs/data_card.md, data/manifests/third_party_downloads.json).

The helpers are tested on synthetic rows first. The committed files are then checked with them: the S10 records
are consistent, keep the file's format, add no URL and name no natural repository (every repository that the S9
and S9x fetch records list by URL, whether or not it became a task); the README carries the AIDev v5 attribution;
the data card's status, counts and statements match the committed records, the index and the natural run's published
analysis, and the paper's ethics section says, as the data card does, how git links tasks to repositories. Where the
git-ignored S10 data exists (the fetch log, the families' s10.json and the wheelhouses) and the private records outside
the repository that the S10 record cites, the records are also checked against them, read only.

A failure names locations, ids, counts and the module's own phrases, never the checked text, a repository, a URL or
a wheel name: each value is computed before its ``assert``, because pytest prints the operands and call arguments
of an assert statement.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

R = Path(__file__).resolve().parents[1]
DOWNLOADS = R / "data" / "manifests" / "third_party_downloads.json"
INDEX = R / "data" / "manifests" / "natural_tasks_index.json"
S9X_MANIFEST = R / "data" / "manifests" / "screening_natural_aidev_s9x.json"
README = R / "THIRD_PARTY_LICENSES" / "README.md"
CARD = R / "docs" / "data_card.md"
ETHICS = R / "paper" / "sections" / "ethics.tex"
NATURAL_RUN = R / "results" / "runs" / "natural-pr-v1" / "analysis.json"
FETCH_LOG = R / "data" / "natural" / "s10_fetch_log.jsonl"
NATURAL_TASKS = R / "data" / "natural" / "tasks"
FETCH_ID, WHEELS_ID = "aidev-v5-s10-repo-fetches", "pypi-natural-s10-wheelhouses"
S9_ID, S9X_ID = "aidev-v5-s9-repo-fetches", "aidev-v5-s9x-repo-fetches"
REQUIRED = ("id", "kind", "source", "version", "license", "license_note", "size_bytes", "local_path", "documented_in",
            "purpose", "contents_note", "third_party_personal_data", "retention", "in_repo")
URL = re.compile(r"https?://[^\s\"'()<>|`]+")
REPO_CAP = 300_000_000
NUMBER = r"(\d[\d,]*)"


def bytes_per_repository(rows: list[dict[str, Any]], until: str) -> dict[int, dict[str, Any]]:
    """The fetch log's operations up to ``until`` (UTC, inclusive), in log order, per repository id: the clone's
    bytes before the first, the bytes added, the bytes after the last, the operations by git subcommand, and
    ``over_cap`` if a cap stopped one (a timeout is not a cap)."""
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        if r["utc"] > until:
            continue
        p = out.setdefault(r["repo_id"], {"aidev_repo_id": r["repo_id"], "status": "fetched",
                                          "bytes_before": r["bytes_before"], "bytes_added": 0,
                                          "size_bytes": r["bytes_before"], "operations": {}})
        p["bytes_added"] += r["bytes_after"] - r["bytes_before"]
        p["size_bytes"] = r["bytes_after"]
        p["operations"][r["subcommand"]] = p["operations"].get(r["subcommand"], 0) + 1
        if r.get("killed") and r["killed"] != "timeout":
            p["status"] = "over_cap"
    return out


def natural_repository_rows(recs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows of the AIDev fetch records that list a repository by URL: every repository that stage S9 or its
    extension screened, whether or not it became a task (a row without a URL, as in the S10 record, is not one)."""
    return [row for rid, rec in recs.items() if rid.startswith("aidev-v5-")
            for row in rec.get("repositories") or [] if row.get("url")]


def natural_repository_words(rows: list[dict[str, Any]]) -> set[str]:
    """The owner and repository names in the rows' URLs; a masked owner (``{owner}``) is not a name."""
    return {w for row in rows for w in row["url"].rstrip("/").split("/")[-2:] if w != "{owner}"}


def github_repository(url: str) -> str | None:
    """``owner/name``, in lower case, of a github.com URL that names a repository (any deeper path, a ``.git``
    suffix and trailing punctuation are ignored), else None."""
    parts = url.rstrip(".,;:").split("/")
    if len(parts) < 5 or parts[2].lower() not in ("github.com", "www.github.com"):
        return None
    name = parts[4].lower().removesuffix(".git")
    return f"{parts[3].lower()}/{name}" if parts[3] and name else None


def whole_words(text: str, words: set[str]) -> set[str]:
    """The ``words`` that occur in ``text`` as whole words, ignoring case (a letter, digit or underscore on either
    side makes it part of another word; a hyphen does not)."""
    return {w for w in words if re.search(rf"(?<![A-Za-z0-9_]){re.escape(w)}(?![A-Za-z0-9_])", text, re.IGNORECASE)}


def lacks(text: str, *phrases: str) -> list[str]:
    """The ``phrases`` that ``text`` does not contain. Called before the ``assert``, so that a failure prints these
    phrases (the module's own, with ids and counts) and never ``text``."""
    return [p for p in phrases if p not in text]


def flat(text: str) -> str:
    """``text`` with every run of white space as one space (the data card wraps its lines)."""
    return " ".join(text.split())


def section(text: str, heading: str) -> str:
    """The lines of the markdown section that starts at the line ``heading``, up to the next heading of its level."""
    lines = text.splitlines()
    start = lines.index(heading)
    level = heading.split(" ", 1)[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].split(" ", 1)[0] == level), len(lines))
    return "\n".join(lines[start:end])


def num(s: str) -> int:
    return int(s.replace(",", ""))


def records() -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in json.loads(DOWNLOADS.read_text(encoding="utf-8"))["records"]}


def index() -> dict[str, Any]:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def first_sample_s11() -> list[str]:
    return sorted(t["task_id"] for t in index()["tasks"] if t.get("s11") and t.get("sample") == "first")


def card_status_row() -> str:
    lines = CARD.read_text(encoding="utf-8").splitlines()
    return next(line for line in lines if line.startswith("| Natural: PR review"))


def stage_rows(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """The fetch log's lines of the stage that ``rec`` records (later lines belong to later stages)."""
    m = re.fullmatch(r"(\S+) to (\S+)", rec["fetched_utc"])
    assert m
    rows = [json.loads(line) for line in FETCH_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r["utc"] <= m.group(2)]


def private_record(rec: dict[str, Any], name: str) -> Path | None:
    """The file or directory outside the repository that ``rec`` cites in documented_in under ``name``."""
    for entry in rec["documented_in"]:
        path = entry.split(" (", 1)[0]
        if path.startswith("/") and path.rstrip("/").endswith(name):
            return Path(path)
    return None


# --------------------------------------------------------------------------- helpers, on synthetic rows


def _op(utc: str, repo: int, sub: str, before: int, after: int, killed: str | None = None) -> dict[str, Any]:
    return {"utc": utc, "repo_id": repo, "subcommand": sub, "bytes_before": before, "bytes_after": after,
            "delta": after - before, "killed": killed}


def test_bytes_per_repository_on_synthetic_rows() -> None:
    rows = [_op("2030-01-01T00:00:01Z", 7, "fetch", 100, 150), _op("2030-01-01T00:00:02Z", 8, "archive", 10, 10),
            _op("2030-01-01T00:00:03Z", 7, "fetch", 150, 400, "the repository cap of 300 bytes"),
            _op("2030-01-01T00:00:04Z", 8, "fetch", 10, 12, "timeout"),
            _op("2030-01-02T00:00:00Z", 7, "fetch", 400, 900)]  # a later stage: left out
    got = bytes_per_repository(rows, until="2030-01-01T23:59:59Z")
    assert got[7] == {"aidev_repo_id": 7, "status": "over_cap", "bytes_before": 100, "bytes_added": 300,
                      "size_bytes": 400, "operations": {"fetch": 2}}
    assert got[8] == {"aidev_repo_id": 8, "status": "fetched", "bytes_before": 10, "bytes_added": 2, "size_bytes": 12,
                      "operations": {"archive": 1, "fetch": 1}}
    assert bytes_per_repository(rows, until="2030-01-01T00:00:00Z") == {}


def test_natural_repository_words_and_whole_words_on_synthetic_records() -> None:
    recs: dict[str, dict[str, Any]] = {
        "aidev-v5-a": {"repositories": [{"aidev_repo_id": 1, "url": "https://example.org/acme/widgetco"},
                                        {"aidev_repo_id": 2, "url": "https://example.org/{owner}/toolkit/"}]},
        "aidev-v5-b": {"repositories": [{"aidev_repo_id": 3, "url": "https://example.org/other/unrelated"},
                                        {"aidev_repo_id": 1, "bytes_added": 5}]},  # no URL: not a listing
        "clone-x": {"repositories": [{"aidev_repo_id": 4, "url": "https://example.org/someone/elsewhere"}]},
        "aidev-v5-c": {"kind": "no repositories"}}
    rows = natural_repository_rows(recs)
    assert sorted(r["aidev_repo_id"] for r in rows) == [1, 2, 3]  # every row with a URL of every AIDev record
    words = natural_repository_words(rows)
    assert words == {"acme", "widgetco", "toolkit", "other", "unrelated"}
    assert whole_words("WidgetCo's toolkit-like kit; acme_corp", words) == {"widgetco", "toolkit"}
    assert whole_words("the toolkits of acmecorp", words) == set()
    assert github_repository("https://github.com/Acme/WidgetCo") == "acme/widgetco"
    for url in ("http://www.github.com/acme/widgetco.git", "https://github.com/acme/widgetco/pull/5",
                "https://github.com/acme/widgetco/."):
        assert github_repository(url) == "acme/widgetco", url
    assert github_repository("https://github.com/acme") is None
    assert github_repository("https://example.org/acme/widgetco") is None


def test_text_helpers_on_synthetic_text() -> None:
    text = "# T\n## A\nx\n### A1\ny\n## B\nz"
    assert section(text, "## A") == "## A\nx\n### A1\ny" and section(text, "## B") == "## B\nz"
    assert flat(" a\n  b  c\n") == "a b c" and num("1,234,567") == 1234567
    assert lacks("one two three", "two", "four", "one two") == ["four"]
    rec = {"documented_in": ["docs/x.md D1", "/srv/w/one.json (outside the repository: a record)", "/srv/w/dir/ (b)"]}
    assert private_record(rec, "one.json") == Path("/srv/w/one.json")
    assert private_record(rec, "dir") == Path("/srv/w/dir") and private_record(rec, "x.md") is None


# --------------------------------------------------------------------------- the committed download records


def test_downloads_file_keeps_its_format_and_unique_ids() -> None:
    text = DOWNLOADS.read_text(encoding="utf-8")
    data = json.loads(text)
    same_format = text == json.dumps(data, indent=2, ensure_ascii=False) + "\n"  # two-space indent, ensure_ascii false
    assert same_format
    ids = [r["id"] for r in data["records"]]
    assert len(ids) == len(set(ids)) and {FETCH_ID, WHEELS_ID} <= set(ids)
    assert ids.index(FETCH_ID) > ids.index(S9_ID)  # appended after the records it builds on
    for rid in (FETCH_ID, WHEELS_ID):
        rec = records()[rid]
        assert all(k in rec for k in REQUIRED), rid
        assert rec["in_repo"] is False and rec["retention"] and rec["license"] in data["license_refs"]


def test_s10_fetch_record_gives_bytes_per_repository_id_only() -> None:
    recs = records()
    rec = recs[FETCH_ID]
    repos = rec["repositories"]
    ids = [r["aidev_repo_id"] for r in repos]
    assert rec["kind"] == "git_partial_fetch" and ids == sorted(set(ids))  # by id, not in the order of the families
    for r in repos:
        # no URL, task id or time per repository (D63)
        assert set(r) <= {"aidev_repo_id", "status", "bytes_before", "bytes_added", "size_bytes", "operations", "note"}
        assert r["size_bytes"] - r["bytes_before"] == r["bytes_added"] >= 0
        assert r["status"] in ("fetched", "over_cap") and sum(r["operations"].values()) >= 1
        assert r["status"] == "fetched" or r["size_bytes"] > REPO_CAP
    assert sum(r["bytes_added"] for r in repos) == rec["size_bytes"]
    task_ids, urls = len(re.findall(r"NP-\d", json.dumps(repos))), len(URL.findall(json.dumps(rec, ensure_ascii=False)))
    assert (task_ids, urls) == (0, 0)  # counts only
    s9 = {r["aidev_repo_id"] for r in recs[S9_ID]["repositories"]}
    first = {t["repo_id"] for t in index()["tasks"] if t.get("sample") == "first"}
    assert set(ids) == first and first <= s9  # the repositories of the first sample's families, all cloned at S9


def test_s10_fetch_record_reconciles_its_start_with_the_s9_record() -> None:
    """bytes_before exceeds the S9 record's sizes; the size_note states by how much, where the bytes came from,
    and the total of all clones before and after the stage."""
    recs = records()
    rec, s9 = recs[FETCH_ID], {r["aidev_repo_id"]: r for r in recs[S9_ID]["repositories"]}
    gaps = {r["aidev_repo_id"]: r["bytes_before"] - s9[r["aidev_repo_id"]]["size_bytes"] for r in rec["repositories"]}
    assert min(gaps.values()) >= 0
    gap, note = sum(gaps.values()), flat(rec["size_note"])
    missing = lacks(note, f"it exceeds the sizes that {S9_ID} lists", f"by {gap:,} bytes")
    assert missing == []
    m = re.search(rf"no record here lists them: {NUMBER} bytes on demand by the diffs of the S9 correction \(\S+; "
                  rf"{NUMBER} bytes into (\d+) clones in all\) and {NUMBER} bytes by the git commands of the D53 scout",
                  note)
    assert m, "the size_note does not say where the bytes between S9 and S10 came from"
    correction_here, correction_all, _, scout = map(num, m.groups())
    assert correction_here + scout == gap and correction_all >= correction_here
    m = re.search(rf"all clones together held {NUMBER} bytes before this stage and {NUMBER} bytes after it", note)
    assert m, "the size_note does not give the size of all clones before and after the stage"
    before, after = map(num, m.groups())
    s9_total = recs[S9_ID]["size_bytes"]
    assert s9_total == sum(r["size_bytes"] for r in s9.values())
    assert before == s9_total + correction_all + scout and after == before + rec["size_bytes"]


def test_s10_wheelhouse_record_gives_counts_and_bytes_per_image() -> None:
    rec = records()[WHEELS_ID]
    images = rec["images"]
    tags = [i["image"] for i in images]
    assert rec["kind"] == "pypi_wheels" and len(tags) == len(set(tags))
    assert sum(i["size_bytes"] for i in images) == rec["size_bytes"]
    rows = {t["task_id"]: t for t in index()["tasks"]}
    for i in images:
        assert set(i) <= {"image", "image_id", "family", "s10_outcome", "wheels", "built_from_sdists", "size_bytes",
                          "image_status", "note"}
        assert re.fullmatch(r"tc-env:[0-9a-f]{16}", i["image"]) and 0 <= i["built_from_sdists"] <= i["wheels"]
        assert i["s10_outcome"] in ("passed", "rejected", "superseded") and i["family"] in rows
        assert (i["image_id"] is None) == (i["s10_outcome"] == "superseded")
        assert i["image_id"] is None or re.fullmatch(r"sha256:[0-9a-f]{64}", i["image_id"])
        assert i["image_status"].startswith("kept") == (i["s10_outcome"] == "passed")
        if i["s10_outcome"] != "superseded":
            assert rows[i["family"]]["s10"]["outcome"] == i["s10_outcome"]
    assert sorted(i["family"] for i in images if i["s10_outcome"] == "passed") == first_sample_s11()
    text = json.dumps(rec, ensure_ascii=False)
    # the wheel names and their sha256 stay in s10.json; only the image ids are hashes here (counts only)
    wheel_names, hashes = text.count(".whl"), len(re.findall(r"[0-9a-f]{64}", re.sub(r"sha256:[0-9a-f]{64}", "", text)))
    assert (wheel_names, hashes) == (0, 0)


def test_s10_wheelhouse_size_note_says_where_each_size_comes_from() -> None:
    rec = records()[WHEELS_ID]
    built = [i for i in rec["images"] if i["s10_outcome"] != "superseded"]
    superseded = [i for i in rec["images"] if i["s10_outcome"] == "superseded"]
    missing = lacks(flat(rec["size_note"]),
                    f"{len(rec['images'])} wheelhouses below: {sum(i['wheels'] for i in rec['images']):,} wheels",
                    f"For the {len(built)} wheelhouses of the families built at S10, size_bytes is s10.json "
                    f"environment.wheelhouse_bytes ({sum(i['size_bytes'] for i in built):,} bytes)",
                    f"for the {len(superseded)} superseded builds, which no s10.json refers to, it is the size of "
                    f"their wheel files on disk ({sum(i['size_bytes'] for i in superseded):,} bytes)")
    assert missing == []


def test_the_name_and_url_guards_cover_every_natural_repository() -> None:
    """The guards below take every repository that the S9 and S9x records list by URL; that covers the repository
    of every family and reserve of both samples (the index and the S9x families), including those not yet built."""
    recs = records()
    rows = natural_repository_rows(recs)
    listed = {r["aidev_repo_id"] for r in rows}
    assert listed == {r["aidev_repo_id"] for rid in (S9_ID, S9X_ID) for r in recs[rid]["repositories"]}
    families = json.loads(S9X_MANIFEST.read_text(encoding="utf-8"))["summary"]["s11_families"]
    task_repos = ({t["repo_id"] for t in index()["tasks"]}
                  | {f["repo_id"] for key in ("family_prs", "reserve_prs") for f in families[key]})
    assert len(task_repos - listed) == 0  # counts only
    n_words, not_github = len(natural_repository_words(rows)), sum(github_repository(r["url"]) is None for r in rows)
    assert n_words > 0 and not_github == 0


def test_new_records_add_no_url() -> None:
    recs = records()
    natural = {r["url"] for r in natural_repository_rows(recs)}
    listed = {u for rid, r in recs.items() if rid not in (FETCH_ID, WHEELS_ID)
              for u in URL.findall(json.dumps(r, ensure_ascii=False))} - natural
    extra = {rid: len(set(URL.findall(json.dumps(recs[rid], ensure_ascii=False))) - listed)
             for rid in (FETCH_ID, WHEELS_ID)}
    assert extra == dict.fromkeys(extra, 0)  # counts only, so that a failure prints no URL


def test_readme_and_data_card_add_no_url_beyond_the_committed_records() -> None:
    recs = records()
    natural = {r["url"] for r in natural_repository_rows(recs)}
    known = {u for path in (DOWNLOADS, INDEX) for u in URL.findall(path.read_text(encoding="utf-8"))} - natural
    extra = {path.name: len(set(URL.findall(path.read_text(encoding="utf-8"))) - known) for path in (README, CARD)}
    assert extra == dict.fromkeys(extra, 0)  # counts only


def test_no_natural_repository_url_outside_the_s9_fetch_records() -> None:
    """A natural repository's URL is written only in the S9 and S9x records' rows: in no other record of the file
    (the S10 records included), and not in the README or the data card."""
    recs = records()
    natural = {github_repository(r["url"]) for r in natural_repository_rows(recs)}
    texts = {rid: json.dumps(rec, ensure_ascii=False) for rid, rec in recs.items() if rid not in (S9_ID, S9X_ID)}
    texts |= {"THIRD_PARTY_LICENSES/README.md": README.read_text(encoding="utf-8"),
              "docs/data_card.md": CARD.read_text(encoding="utf-8")}
    found = {where: sum(github_repository(u) in natural for u in set(URL.findall(text)))
             for where, text in texts.items()}
    assert found == dict.fromkeys(texts, 0)  # counts only


def test_records_readme_and_data_card_name_no_natural_repository() -> None:
    recs = records()
    words = natural_repository_words(natural_repository_rows(recs))
    texts = {FETCH_ID: json.dumps(recs[FETCH_ID], ensure_ascii=False),
             WHEELS_ID: json.dumps(recs[WHEELS_ID], ensure_ascii=False),
             "THIRD_PARTY_LICENSES/README.md": README.read_text(encoding="utf-8"),
             "docs/data_card.md": CARD.read_text(encoding="utf-8")}
    found = {where: len(whole_words(text, words)) for where, text in texts.items()}
    assert found == dict.fromkeys(texts, 0)  # counts only, so that a failure prints no name


# --------------------------------------------------------------------------- licences and data card


def test_readme_attributes_aidev_and_states_the_natural_code_rule() -> None:
    text = README.read_text(encoding="utf-8")
    src = index()["source"]
    row = next(line for line in text.splitlines() if line.startswith("| AIDev v5"))
    missing = lacks(row, src["dataset"], src["revision"], src["url"], src["licence"], src["licence_url"],
                    src["attribution"], "Extracted, not copied", "No verbatim comment, pull-request or issue text")
    missing += lacks(text, "**No upstream code of a natural repository is in git.**")
    assert missing == []


def test_data_card_status_counts_the_accepted_tasks_of_both_samples() -> None:
    row, idx = card_status_row(), index()
    accepted = sorted(t["task_id"] for t in idx["tasks"] if t.get("s11"))
    assert len(accepted) == sum(idx["s11_by_sample"].values())  # the index's own count over both samples
    first = [t["s10"]["outcome"] for t in idx["tasks"] if t.get("sample") == "first"]
    missing = lacks(row, f"**{len(accepted)} tasks accepted** (S11: {', '.join(accepted)})",
                    "S9 extension under protocol v0.11",
                    f"Stage S10 of the first sample is in `natural_tasks_index.json` (its {len(first)} rows: "
                    f"{first.count('passed')} passed, {first.count('rejected')} rejected, "
                    f"{first.count('not built')} not built)")
    assert accepted and missing == []
    # Each run is reported on its own (protocol v0.12, §20.3): the size rule counts the run's own accepted tasks.
    in_run = json.loads(NATURAL_RUN.read_text(encoding="utf-8"))["meta"]["case_study"]["accepted_in_run"]
    case_study = (f"`natural-pr-v1` grades {in_run} accepted tasks of its own, fewer than 10, so its families are "
                  "per-family exploratory case studies (§19.6, §20.3)")
    says_case_study = case_study in row
    assert says_case_study == (in_run < 10)


def test_data_card_counts_the_s9_repository_urls() -> None:
    recs = records()
    s9, s9x = recs[S9_ID]["repositories"], recs[S9X_ID]["repositories"]
    distinct = {r["aidev_repo_id"] for r in s9 + s9x}
    refused = [{r["aidev_repo_id"] for r in rows if r["status"] == "clone_failed"} for rows in (s9, s9x)]
    assert refused[0] == refused[1]  # the same repositories in both lists
    masked = [sum("{owner}" in r["url"] for r in rows) for rows in (s9, s9x)]
    masked_distinct = len({r["aidev_repo_id"] for r in s9 + s9x if "{owner}" in r["url"]})
    missing = lacks(flat(CARD.read_text(encoding="utf-8")),
                    f"the URLs of the repositories of stage S9 in `third_party_downloads.json`: {len(s9)} for the "
                    f"first sample and {len(s9x)} for the extension, {len(distinct)} distinct. The same "
                    f"{len(refused[0])} of them are in both lists and were never fetched: the proxy refused them "
                    "(status `clone_failed`)",
                    f"({masked[0]} of the first sample's {len(s9)} URLs and {masked[1]} of the extension's "
                    f"{len(s9x)}; {masked_distinct} of the {len(distinct)} distinct repositories)")
    missing += lacks(card_status_row(), "the URLs of the repositories screened at S9 (see Personal information)")
    assert missing == []


def test_data_card_says_which_urls_the_index_holds() -> None:
    src = index()["source"]
    others = len(set(URL.findall(INDEX.read_text(encoding="utf-8"))) - {src["url"], src["licence_url"]})
    assert others == 0  # no repository URL in the index (counts only)
    missing = lacks(flat(CARD.read_text(encoding="utf-8")),
                    "with no thread text, login, repository URL or repository file path; its only URLs are those "
                    "of the dataset and its licence")
    assert missing == []


def test_data_card_and_s10_record_say_how_git_links_tasks_to_repositories() -> None:
    """The download records carry no task id, but the index's repo_id joins every task to a URL row: both texts
    say so, as the paper's ethics section does, and none of the three claims that nothing in git links a repository
    to a task."""
    recs, idx = records(), index()
    listed = {r["aidev_repo_id"] for r in natural_repository_rows(recs)}
    joined = sum(t["repo_id"] in listed for t in idx["tasks"])
    assert joined == len(idx["tasks"]) > 0
    personal = flat(section(CARD.read_text(encoding="utf-8"), "## Personal information"))
    note = flat(recs[FETCH_ID]["contents_note"])
    missing = lacks(personal, "The S9 and S9x download records themselves hold no task id or comment (D63)",
                    "Git does link tasks and comments to repositories through ids: `natural_tasks_index.json` gives "
                    "every task's `repo_id` and the S9 and S9x screening manifests every screened comment's")
    missing += lacks(note, "This record carries no task id and no time per repository",
                     "data/manifests/natural_tasks_index.json does, through each task's repo_id")
    ethics = flat(ETHICS.read_text(encoding="utf-8"))
    missing += lacks(ethics, "the release links each natural task and screened comment to its repository")
    assert missing == []
    stale = ("link no repository to a task", "No record here links a repository to a task",
             "no record links a repository to a task", "download records themselves name no task, comment or person")
    claims = sum(s in personal or s in note or s in ethics for s in stale)
    assert claims == 0


# --------------------------------------------------------------------------- against the git-ignored S10 data


@pytest.mark.skipif(not FETCH_LOG.is_file(), reason="no S10 fetch log here (data/natural/ is git-ignored)")
def test_s10_fetch_record_matches_the_fetch_log() -> None:
    rec = records()[FETCH_ID]
    stage = stage_rows(rec)
    start = rec["fetched_utc"].split(" to ")[0]
    assert stage and min(r["utc"] for r in stage) == start and all(r["exit"] == 0 for r in stage)
    want = {r["aidev_repo_id"]: {k: v for k, v in r.items() if k != "note"} for r in rec["repositories"]}
    assert bytes_per_repository(stage, until=stage[-1]["utc"]) == want
    assert sum(r["bytes_after"] - r["bytes_before"] for r in stage) == rec["size_bytes"]
    missing = lacks(rec["size_note"], f"over the {len(stage)} operations")
    assert missing == []


@pytest.mark.skipif(not FETCH_LOG.is_file(), reason="no S10 fetch log here (data/natural/ is git-ignored)")
def test_s10_fetch_record_says_which_operation_ran_outside_the_watchdog() -> None:
    """The stage's first operation, a cat-file probe, ran outside the watchdog (its log line says so); the record
    gives its blobs and bytes and does not claim that the watchdog guarded every fetch."""
    rec = records()[FETCH_ID]
    stage, note = stage_rows(rec), flat(rec["contents_note"])
    lazy = sum(bool(r.get("lazy")) for r in stage)
    unwatched = [k for k, r in enumerate(stage) if "not under the watchdog" in r["label"]]
    assert unwatched == [0] and stage[0]["subcommand"] == "cat-file"  # only the first operation
    missing = lacks(note, f"{len(stage) - lazy} explicit fetches of blobs by id", f"{lazy} lazy fetches",
                    f"the stage's first operation ({stage[0]['objects']} blobs, {stage[0]['delta']:,} bytes)",
                    "Every operation but the first ran under a watchdog", "the cat-file probe, ran outside it")
    assert missing == []


@pytest.mark.skipif(not FETCH_LOG.is_file(), reason="no S10 fetch log here (data/natural/ is git-ignored)")
def test_s10_fetch_record_describes_its_archive_fetches() -> None:
    """The archives as the log has them: the pathspec archive of a monorepo package before D59's fix, with its
    bytes in the contents_note, the purpose and its repository's row, and the two small archives."""
    rec = records()[FETCH_ID]
    stage, note = stage_rows(rec), flat(rec["contents_note"])
    archives = [k for k, r in enumerate(stage) if r["subcommand"] == "archive"]
    k = max(archives, key=lambda j: stage[j]["delta"])
    big, before = stage[k], stage[k - 1]  # the explicit fetch of the package's blobs just before it
    is_base_tree = before["repo_id"] == big["repo_id"] and before["label"].startswith("base tree")
    blobs = re.search(r"\((\d+) blobs\)", before["label"])
    assert is_base_tree and blobs
    row = next(r for r in rec["repositories"] if r["aidev_repo_id"] == big["repo_id"])
    small = sorted(stage[j]["delta"] for j in archives if j != k)
    missing = lacks(note, f"and {len(archives)} by git archive of a base",
                    f"in repository {big['repo_id']} as the commit with the package's directory as a pathspec, "
                    "before D59's compiler fix",
                    f"here {big['delta']:,} bytes ({100 * big['delta'] / rec['size_bytes']:.1f}% of this stage and "
                    f"{100 * big['delta'] / row['bytes_added']:.1f}% of what it added to that clone)",
                    f"whose {blobs.group(1)} blobs had been fetched by id just before ({before['delta']:,} bytes)",
                    "the later archives in that repository fetched nothing",
                    f"The other {len(small)} archived bases that are not monorepo packages and fetched "
                    f"{' and '.join(f'{d:,}' for d in small)} bytes")
    missing += lacks(rec["purpose"], f"{big['delta']:,} bytes of blobs of a monorepo commit outside the package")
    missing += lacks(row.get("note", ""), f"{big['delta']:,} of the bytes added came from one git archive")
    assert missing == []
    later = sum(stage[j]["repo_id"] == big["repo_id"] for j in archives if j > k)
    assert later == 0  # a lazy run is logged only when the clone grows: the later archives there fetched nothing
    monorepo = {t["repo_id"] for t in index()["tasks"] if t.get("monorepo_package")}
    small_in_monorepo = sum(stage[j]["repo_id"] in monorepo for j in archives if j != k)
    assert big["repo_id"] in monorepo and small_in_monorepo == 0


@pytest.mark.skipif(not NATURAL_TASKS.is_dir(), reason="no natural tasks here (data/natural/ is git-ignored)")
def test_s10_wheelhouse_record_matches_every_built_familys_s10() -> None:
    """One entry per first-sample family with an S10 image, equal to its s10.json; a superseded build is one that
    no s10.json refers to. A family rebuilt after the record was written fails here until the record is updated."""
    rec = records()[WHEELS_ID]
    first = {t["task_id"] for t in index()["tasks"] if t.get("sample") == "first"}
    s10 = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in NATURAL_TASKS.glob("NP-*/s10.json")}
    built = {f: e for f, e in s10.items() if (e.get("environment") or {}).get("image")}
    current = [i for i in rec["images"] if i["s10_outcome"] != "superseded"]
    entries = {i["family"]: i for i in current}
    assert len(entries) == len(current)  # one entry per family
    assert sorted(entries) == sorted(f for f in built if f in first)
    differ = []
    for fam, i in entries.items():
        env = built[fam]["environment"]
        got = (env["image"], env["image_id"], len(env["files"]), env["wheelhouse_bytes"],
               len(env.get("sdist_builds") or []), built[fam]["outcome"])
        if got != (i["image"], i["image_id"], i["wheels"], i["size_bytes"], i["built_from_sdists"], i["s10_outcome"]):
            differ.append(fam)
    assert differ == []
    in_use = {e["environment"]["image"] for e in built.values()}
    referred = sum(i["image"] in in_use for i in rec["images"] if i["s10_outcome"] == "superseded")
    assert referred == 0


def test_s10_wheelhouse_record_matches_the_wheelhouses_on_disk() -> None:
    """Every entry's wheel count and bytes are its wheelhouse's on disk; each superseded build shares the most wheel
    file names with its own family's current wheelhouse, as its note says (names are compared, never printed)."""
    rec = records()[WHEELS_ID]
    cache, template = Path(rec["local_path"]).parent, Path(rec["local_path"]).name
    if not cache.is_dir():
        pytest.skip("no wheelhouse cache here (it is outside the repository)")
    names: dict[str, set[str]] = {}
    differ = []
    for i in rec["images"]:
        wh = cache / template.replace("<image hash>", i["image"].split(":", 1)[1])
        wheels = sorted(wh.glob("*.whl"))
        names[i["image"]] = {w.name for w in wheels}
        on_disk = (len(wheels), sum(w.stat().st_size for w in wheels))
        if not (wh / ".complete").is_file() or on_disk != (i["wheels"], i["size_bytes"]):
            differ.append(i["image"])
    assert differ == []
    current = {i["family"]: names[i["image"]] for i in rec["images"] if i["s10_outcome"] != "superseded"}
    for i in rec["images"]:
        if i["s10_outcome"] != "superseded":
            continue
        own = names[i["image"]]
        shared = {f: len(own & n) for f, n in current.items()}
        closest = max(shared, key=lambda f: shared[f])
        assert closest == i["family"], i["image"]
        both, more = shared[i["family"]], len(current[i["family"]] - own)
        said = f"All of its {len(own)}" if both == len(own) else f"{both} of its {len(own)}"
        missing = lacks(i.get("note", ""), f"{said} wheel file names are in {i['family']}'s current wheelhouse, "
                                           f"which holds {more} more")
        assert missing == [], i["image"]


# --------------------------------------------------------------------------- against the private records it cites


def test_s10_fetch_record_reconciles_with_the_private_records_it_cites() -> None:
    """Per repository: the S9 record's size, plus the S9 correction's on-demand fetches and the D53 scout's, gives
    the S10 record's bytes_before; and the scout's PyPI downloads are the bound the wheelhouse record states."""
    recs = records()
    rec = recs[FETCH_ID]
    correction, scout = private_record(rec, "s9_correction_record.json"), private_record(rec, "s10_scout")
    assert correction and scout and private_record(recs[WHEELS_ID], "s10_scout") == scout  # cited in documented_in
    if not (correction.is_file() and (scout / "half_1.json").is_file() and (scout / "half_2.json").is_file()):
        pytest.skip("the private records are not here (they are outside the repository)")
    fetches = json.loads(correction.read_text(encoding="utf-8"))["fetches"]["repositories"]
    added = {f["aidev_repo_id"]: f["bytes_at_record_time"] - f["bytes_before"] for f in fetches}
    halves = [json.loads((scout / f"half_{k}.json").read_text(encoding="utf-8"))["fetch_record"] for k in (1, 2)]
    by_scout: dict[int, int] = {}
    for half in halves:
        for repo, b in half["git"]["by_repository"].items():
            by_scout[int(repo)] = by_scout.get(int(repo), 0) + b["bytes_added"]
    s9 = {r["aidev_repo_id"]: r["size_bytes"] for r in recs[S9_ID]["repositories"]}
    here = {r["aidev_repo_id"] for r in rec["repositories"]}
    differ = [r["aidev_repo_id"] for r in rec["repositories"]
              if s9[r["aidev_repo_id"]] + added.get(r["aidev_repo_id"], 0) + by_scout.get(r["aidev_repo_id"], 0)
              != r["bytes_before"]]
    outside = len(set(by_scout) - here)
    assert differ == [] and outside == 0
    pypi = sum(h["downloads_bytes_upper_bound"] for h in halves)
    missing = lacks(flat(rec["size_note"]),
                    f"{sum(v for k, v in added.items() if k in here):,} bytes on demand by the diffs of the S9 "
                    "correction",
                    f"{sum(added.values()):,} bytes into {len(added)} clones in all",
                    f"{sum(by_scout.values()):,} bytes by the git commands of the D53 scout")
    missing += lacks(flat(recs[WHEELS_ID]["contents_note"]), f"at most {pypi:,} bytes, D53's 572 MB")
    assert missing == []
