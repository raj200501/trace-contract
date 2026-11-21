"""Static, self-contained HTML report built only from recorded artifacts.

``build_report(run_dir, tasks_root, repo_root, out)`` renders, for every task in a
run: the user turns of the source session, the requirement contracts side by side
(initial-only, correction-aware, reference), every evaluated candidate with its
label and patch, and the verifier x candidate outcome matrix with failing checks
and diagnostics. Numbers come from ``analysis.json``; nothing is typed in by hand.

The banners name the run's populations (from the analysis, else the tasks' manifests), and a
run that pools populations says so and shows each population's table (``by_population``), as
it shows each candidate stratum's (``by_stratum``). A stratum candidate is shown with its
stratum; a fresh attempt that the analysis excludes is marked as excluded. An analysis under
the reporting rules of a new run (``meta.reporting_rules``, protocol §15.7) is shown as those
rules ask: the per-family table first, exact sign-flip p-values with their floors, the null
results with them, and the cluster-bootstrap intervals in an appendix. A run recorded before
these features (``pilot-v0.3.3``) renders as it did.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .schemas import Candidate, TaskContract, TaskManifest, VerificationResult, VerifierSpec
from .store import load, read_jsonl
from .strata import run_stratum_candidates

CSS = """
:root { --bg:#ffffff; --fg:#1d1d1f; --muted:#5f6368; --line:#d9dce1; --card:#f6f7f9; --pass:#1a7f37; --fail:#b42318;
        --warn:#9a6700; --accent:#2f5bd3; --code:#f2f3f5; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#111317; --fg:#e8eaed; --muted:#a0a4ab;
        --line:#2e323a; --card:#1a1d23; --pass:#4ac26b; --fail:#ff7b72; --warn:#d29922; --accent:#7aa2ff; --code:#1f232a; } }
:root[data-theme="dark"] { --bg:#111317; --fg:#e8eaed; --muted:#a0a4ab; --line:#2e323a; --card:#1a1d23; --pass:#4ac26b;
        --fail:#ff7b72; --warn:#d29922; --accent:#7aa2ff; --code:#1f232a; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
main { max-width:1180px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:20px; margin:36px 0 10px; border-bottom:1px solid var(--line); padding-bottom:6px; }
h3 { font-size:16px; margin:22px 0 8px; } .muted { color:var(--muted); }
.banner { background:var(--card); border-left:4px solid var(--warn); padding:10px 14px; margin:14px 0; border-radius:6px; }
table { border-collapse:collapse; width:100%; margin:8px 0 14px; font-size:13.5px; }
th, td { border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }
th { background:var(--card); font-weight:600; }
.scroll { overflow-x:auto; }
.pass { color:var(--pass); font-weight:600; } .fail { color:var(--fail); font-weight:600; } .infra { color:var(--warn); font-weight:600; }
pre { background:var(--code); padding:10px; border-radius:6px; overflow-x:auto; font-size:12.5px; line-height:1.4; max-height:420px; }
details { margin:6px 0; } summary { cursor:pointer; }
.turn { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:8px 0; white-space:pre-wrap; }
.tag { display:inline-block; padding:1px 7px; border-radius:10px; background:var(--card); border:1px solid var(--line); font-size:12px; margin-right:4px; }
"""


ORDER = ["initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform", "repo_tests", "diff_derived"]
NAMES = {"initial_plain": "C1 initial-only, plain", "initial_audited": "C2 initial-only, audited",
         "full_plain": "C3 correction-aware, plain", "full_audited": "C4 correction-aware, audited",
         "llm_freeform": "B2 full-session LLM", "repo_tests": "B1 repository tests", "diff_derived": "B3 diff-derived"}
# What each population's tasks are, for the banners: (name, description).
POPULATIONS = {
    "controlled": ("controlled", "real agent runs with scripted user turns, not natural user traffic"),
    "natural": ("natural", "sessions of real users with a coding agent"),
    "natural:pr-review": ("natural PR-review", "agent pull requests in which a reviewer's comment takes the place of the "
                          "user's correction; the reviewer is often not the requester"),
    "natural:chat": ("natural chat", "sessions of real users with a coding agent, from an ungated source"),
    "fixture": ("fixture", "hand-written synthetic tasks, not research data"),
}


def _ordered(d: dict) -> list:
    return [(k, d[k]) for k in ORDER if k in d] + [(k, v) for k, v in d.items() if k not in ORDER]


def _cname(c: str) -> str:
    return f"{NAMES.get(c, c)} <span class='muted'>({c})</span>" if c in NAMES else c


def _e(s) -> str:
    return html.escape("" if s is None else str(s))


def _cls(outcome: str) -> str:
    return "pass" if outcome == "pass" else "fail" if outcome == "task_failure" else "infra"


def _rate(d: dict, ci: bool = True) -> str:
    if d.get("rate") is None:
        return f"n/a (0/{d.get('den', 0)})"
    s = f"{d['rate']:.2f} ({d['num']}/{d['den']})"
    if ci and d.get("ci95"):
        s += f" [{d['ci95'][0]:.2f}, {d['ci95'][1]:.2f}]" + ("*" if d.get("ci95_degenerate") else "")
    return s


def _p(x) -> str:
    return "—" if x is None else f"{x:.3g}"


def _population_sentence(pops: list[str]) -> str:
    """What the run's tasks are, named by their populations; never 'controlled' for a natural run."""
    if pops == ["controlled"]:
        return "Sessions are <b>controlled</b> (real agent runs with scripted user turns), not natural user traffic."
    described = [(POPULATIONS.get(p, (p, "a population without a description"))) for p in pops]
    if len(described) == 1:
        return f"Tasks are <b>{_e(described[0][0])}</b> ({_e(described[0][1])})."
    return (f"Tasks come from {len(pops)} populations, reported separately below: "
            + "; ".join(f"<b>{_e(n)}</b> ({_e(d)})" for n, d in described) + ".")


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def _group_tables(title: str, intro: str, groups: dict, ci: bool) -> str:
    """One table per population or candidate stratum (``by_population``, ``by_stratum``; the task's own stratum first)."""
    out = [f"<h3>{_e(title)}</h3><p class='muted'>{intro}</p>"]
    for g, d in sorted(groups.items(), key=lambda kv: (kv[0] != "task", kv[0])):
        out.append(f"<h4>{_e(g)} <span class='muted'>(tasks: {_e(', '.join(d['tasks']))}; families: {d['n_families']})</span></h4>"
                   "<div class='scroll'><table><tr><th>Condition</th><th>False acceptance</th><th>FA exact 95%</th>"
                   "<th>False rejection</th><th>FR exact 95%</th><th>Infrastructure outcomes</th><th>Excluded (unlabeled/ambiguous)</th></tr>")
        for c, x in _ordered(d["conditions"]):
            fa, fr = x["false_acceptance"], x["false_rejection"]
            out.append(f"<tr><td>{_cname(c)}</td><td>{_rate(fa, ci)}</td><td>{_iv(fa.get('exact95'))}</td><td>{_rate(fr, ci)}</td>"
                       f"<td>{_iv(fr.get('exact95'))}</td><td>{x['infrastructure']['num']}/{x['infrastructure']['den']}</td>"
                       f"<td>{x['excluded_unlabeled_or_ambiguous']}</td></tr>")
        out.append("</table></div>")
    return "".join(out)


def _signflip_table(comparisons: list[dict], heading: str) -> str:
    """Paired comparisons with exact sign-flip p-values over families and their floors, and the null results (§15.7)."""
    out = [f"{heading}<div class='scroll'><table><tr><th>A</th><th>B</th><th>Metric</th><th>A − B</th><th>Per-family A − B</th>"
           "<th>p (A &gt; B)</th><th>p (A &lt; B)</th><th>p two-sided</th><th>p two-sided, family means</th>"
           "<th>Floor one-sided / two-sided</th><th>Families</th></tr>"]
    for d in comparisons:
        sf, sm = d["signflip"]["pooled"], d["signflip"]["family_mean"]
        per = ", ".join(f"{_e(f)} {(x['a_num'] - x['b_num']) / x['den']:+.2f}" for f, x in d["per_family_counts"].items()
                        if x["den"]) or "—"
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        out.append(f"<tr><td>{_e(d['a'])}</td><td>{_e(d['b'])}</td><td>{d['metric'].upper()}</td><td>{diff}</td><td>{per}</td>"
                   f"<td>{_p(sf['p_greater'])}</td><td>{_p(sf['p_less'])}</td><td>{_p(sf['p_two_sided'])}</td>"
                   f"<td>{_p(sm['p_two_sided'])}</td><td>{_p(sf['floor_one_sided'])} / {_p(sf['floor_two_sided'])}</td>"
                   f"<td>{sf['k']}</td></tr>")
    tested = [d for d in comparisons if d["signflip"]["pooled"]["k"]]
    null = [d for d in tested if d["signflip"]["pooled"]["p_two_sided"] >= 0.05]
    text = (f"<b>Null results.</b> {len(null)} of {len(tested)} tested comparisons have a two-sided exact p-value of 0.05 or more"
            + (": " + "; ".join(f"{_e(d['a'])} vs {_e(d['b'])} {d['metric'].upper()}" for d in null) if null else ""))
    floors = [d["signflip"]["pooled"]["floor_two_sided"] for d in tested]
    if floors and min(floors) >= 0.05:
        text += f". No two-sided p-value can go below {min(floors):.3g} with this few families, so none can reach 0.05"
    out.append(f"</table></div><p>{text}.</p>")
    return "".join(out)


def _new_run_summary(analysis: dict) -> str:
    """The banner, per-family primary table and exact paired comparisons of a new run (protocol §15.7)."""
    rr, bs, dp = analysis["meta"]["reporting_rules"], analysis["meta"]["bootstrap"], analysis["distinct_patches"]
    boot = "" if bs["inferential"] else f", marked as not inferential ({bs['n_families']} task families, fewer than 10)"
    out = [f"<div class='banner'><b>Reporting rules of a new run</b> (protocol §15.7, §16.6): {_e(rr['basis'])}. Each distinct "
           f"graded patch counts once ({dp['n_distinct']} distinct among {dp['n_heldout']} held-out candidates). The per-family "
           "table is the primary display, every paired comparison carries exact sign-flip p-values over task families with their "
           f"attainable floors, and the cluster-bootstrap intervals are in the appendix{boot}.</div>"]
    fams = sorted({f for d in analysis["per_family"].values() for f in d})
    out.append("<h2>Primary display: rates per task family</h2><p class='muted'>(num/den) per task family, each distinct graded "
               "patch once; reference solution and no-op excluded (sanity table below).</p><div class='scroll'><table><tr>"
               "<th>Condition</th>" + "".join(f"<th>{_e(f)} FA</th><th>{_e(f)} FR</th>" for f in fams) + "<th>All FA</th><th>All FR</th></tr>")
    for c, pf in _ordered(analysis["per_family"]):
        cells = "".join("<td>—</td><td>—</td>" if f not in pf else
                        f"<td>{pf[f]['fa_num']}/{pf[f]['fa_den']}</td><td>{pf[f]['fr_num']}/{pf[f]['fr_den']}</td>" for f in fams)
        d = analysis["conditions"][c]
        out.append(f"<tr><td>{_cname(c)}</td>{cells}<td>{_rate(d['false_acceptance'], False)}</td>"
                   f"<td>{_rate(d['false_rejection'], False)}</td></tr>")
    out.append("</table></div>")
    out.append(_signflip_table(analysis["comparisons"], "<h3>Paired comparisons: exact sign-flip tests over task families</h3>"
                               "<p class='muted'>Same candidates, each distinct graded patch once. The p-values test the sum over "
                               "families of the count differences (each candidate weighs the same); the family-mean column weighs each "
                               "family the same. p (A &gt; B): the first-named condition errs more.</p>"))
    return "".join(out)


def _new_run_sections(analysis: dict) -> str:
    """The oracle-gated view and the distinct graded patches of a new run."""
    o = analysis["oracle_gated"]
    out = [f"<h3>Oracle-gated view (secondary)</h3><p class='muted'>{_e(_sentence(o['rule']))}.</p><div class='scroll'><table><tr>"
           "<th>Condition</th><th>Cells kept</th><th>Dropped</th><th>Lost yield (invalid / valid)</th><th>False acceptance</th>"
           "<th>False rejection</th></tr>"]
    for c, d in _ordered(o["conditions"]):
        dropped = "; ".join(f"{_e(t)}: {_e(why)}" for t, why in d["dropped"].items()) or "—"
        out.append(f"<tr><td>{_cname(c)}</td><td>{d['cells_kept']}/{d['cells']}</td><td>{dropped}</td>"
                   f"<td>{d['lost_yield']['invalid']} / {d['lost_yield']['valid']}</td><td>{_rate(d['false_acceptance'], False)}</td>"
                   f"<td>{_rate(d['false_rejection'], False)}</td></tr>")
    out.append("</table></div>")
    if o["comparisons"]:
        out.append(_signflip_table(o["comparisons"], "<h4>Oracle-gated paired comparisons</h4><p class='muted'>Same candidates, on "
                                                     "the tasks that both conditions keep.</p>"))
    dp = analysis["distinct_patches"]
    groups = "".join(f"<li>{_e(g['task_id'])}: {_e(', '.join(g['members']))} count once, as {_e(g['representative'])} (label "
                     f"{_e(g['label'] or 'none')}{'' if g['labels_agree'] else '; the labels disagree'}"
                     f"{'; outcomes differ under ' + _e(', '.join(g['outcomes_differ'])) if g['outcomes_differ'] else ''})</li>"
                     for g in dp["groups"])
    out.append(f"<h3>Distinct graded patches</h3><p class='muted'>{dp['n_distinct']} distinct graded patches among "
               f"{dp['n_heldout']} held-out candidates: {_e(dp['rule'])}.</p>" + (f"<ul>{groups}</ul>" if groups else ""))
    return "".join(out)


def _fresh_section(f: dict) -> str:
    """Solve rates of the fresh attempts by configuration and variant, and the excluded attempts (protocol §15.4)."""
    out = [f"<h3>Fresh-agent attempts</h3><p class='muted'>{_e(_sentence(f['rule']))}.</p><div class='scroll'><table><tr><th>Configuration</th>"
           "<th>Variant</th><th>Attempts</th><th>Solved</th><th>Not solved</th><th>Undecided</th><th>Solve rate</th>"
           "<th>Finished / gave up / error</th><th>Per family (solved/attempts)</th></tr>"]
    for d in f["by_configuration_variant"].values():
        e = d["ended"]
        per = ", ".join(f"{_e(fam)} {x['solved']}/{x['attempts']}" for fam, x in d["per_family"].items())
        out.append(f"<tr><td>{_e(d['configuration'])}</td><td>{_e(d['variant'])}</td><td>{d['attempts']}</td><td>{d['solved']}</td>"
                   f"<td>{d['not_solved']}</td><td>{d['undecided']}</td><td>{d['rate']:.2f}</td>"
                   f"<td>{e.get('finished', 0)} / {e.get('gave_up', 0)} / {e.get('error', 0)}</td><td>{per}</td></tr>")
    out.append("</table></div>")
    if f["excluded"]:
        out.append(f"<p>Excluded from every analysis ({len(f['excluded'])}): " + "; ".join(
            f"{_e(x['candidate_id'])} ({_e(x['reason'])})" for x in f["excluded"]) + ".</p>")
    else:
        out.append("<p class='muted'>No attempt is excluded.</p>")
    return "".join(out)


def _source_section(s: dict) -> str:
    out = [f"<h3>Source-evidence labels (reported apart from D19)</h3><p class='muted'>{_e(_sentence(s['rule']))}.</p><div class='scroll'>"
           "<table><tr><th>Condition</th><th>Invalid by source evidence, accepted</th><th>Valid by source evidence, rejected</th></tr>"]
    for c, d in _ordered(s["conditions"]):
        out.append(f"<tr><td>{_cname(c)}</td><td>{d['invalid']['accepted']}/{d['invalid']['n']}</td>"
                   f"<td>{d['valid']['rejected']}/{d['valid']['n']}</td></tr>")
    out.append("</table></div>")
    return "".join(out)


def _bootstrap_appendix(analysis: dict) -> str:
    """The cluster-bootstrap intervals of a new run, marked as not inferential below 10 families (protocol §15.7)."""
    bs = analysis["meta"]["bootstrap"]
    mark = "" if bs["inferential"] else (f" <b>Not inferential:</b> the run has {bs['n_families']} task families, fewer than 10.")
    out = [f"<h2>Appendix: cluster-bootstrap intervals</h2><p class='muted'>95% percentile intervals of a bootstrap that resamples "
           f"task families (each distinct graded patch once); * marks a degenerate interval.{mark}</p><div class='scroll'><table>"
           "<tr><th>Condition</th><th>False acceptance [95% bootstrap]</th><th>False rejection [95% bootstrap]</th></tr>"]
    for c, d in _ordered(analysis["conditions"]):
        out.append(f"<tr><td>{_cname(c)}</td><td>{_rate(d['false_acceptance'])}</td><td>{_rate(d['false_rejection'])}</td></tr>")
    out.append("</table></div><div class='scroll'><table><tr><th>A</th><th>B</th><th>Metric</th><th>A − B</th><th>95% bootstrap</th>"
               "<th>Families</th></tr>")
    for d in analysis["comparisons"]:
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]" + ("*" if d.get("ci95_degenerate") else "")
        out.append(f"<tr><td>{_e(d['a'])}</td><td>{_e(d['b'])}</td><td>{d['metric'].upper()}</td><td>{diff}</td><td>{ci}</td>"
                   f"<td>{d['n_families']}</td></tr>")
    out.append("</table></div>")
    for title, key in (("By population", "by_population"), ("By candidate stratum", "by_stratum")):
        if analysis.get(key):
            out.append(_group_tables(f"{title} (bootstrap intervals)", "Groups with fewer than 10 task families are not inferential.",
                                     analysis[key], True))
    return "".join(out)


def _iv(x) -> str:
    return "—" if not x else f"[{x[0]:.2f}, {x[1]:.2f}]"


def _licence_notices(manifest: dict, tasks_root: Path, repo_root: Path) -> str:
    """Embed the upstream licence notices: this file contains upstream code (the candidate diffs)."""
    rows = []
    for t in manifest["tasks"]:
        m = load(tasks_root / t["task_id"] / "task.json", TaskManifest)
        project = m.snapshot_source.repo_url.rstrip("/").split("/")[-1]
        f = repo_root / "THIRD_PARTY_LICENSES" / f"{project}.txt"
        if f.is_file():
            rows.append(f"<details><summary>{_e(project)} ({_e(m.snapshot_source.repo_url)} @ "
                        f"<code>{_e(m.snapshot_source.commit[:12])}</code>)</summary><pre>{_e(f.read_text(encoding='utf-8'))}</pre></details>")
    if not rows:
        return ""
    return ("<h2>Third-party licence notices</h2><p class='muted'>The candidate patches above contain code of the upstream "
            "projects at the pinned commits. Their copyright and permission notices follow and must accompany copies of this "
            "file (also in <code>THIRD_PARTY_LICENSES/</code>).</p>" + "".join(rows))


def _label(c: Candidate, analysis: dict):
    """The label the analysis used (its label rule); for excluded candidates, the latest proposal.

    A candidate whose human reviewers disagree without adjudication shows no label, never
    one reviewer's (decision log D46).
    """
    from .analysis import candidate_label

    if c.human_disagreement():
        return None
    return candidate_label(c, analysis["meta"].get("label_rule", "human")) or c.final_label() or c.proposed_label()


def build_report(run_dir: Path, tasks_root: Path, repo_root: Path, out: Path) -> Path:
    from .tasks import session_for_task

    from .analysis import attempt_exclusion

    analysis = json.loads((run_dir / "analysis.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    results = read_jsonl(run_dir / "results.jsonl", VerificationResult)
    meta = analysis["meta"]
    new = "reporting_rules" in meta  # a new run: the reporting rules of protocol §15.7
    pops = sorted(meta.get("populations") or {load(tasks_root / t["task_id"] / "task.json", TaskManifest).population.value
                                              for t in manifest["tasks"]})
    strata_of = {t["task_id"]: run_stratum_candidates(tasks_root / t["task_id"], t) for t in manifest["tasks"]}
    with_strata = any(strata_of.values())
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>TraceContract Run Report</title><style>{CSS}</style></head><body><main>",
             f"<h1>TraceContract run report</h1><div class='muted'>run <code>{_e(manifest['run_id'])}</code> · code {_e(manifest.get('code_revision'))} · "
             f"started {_e(manifest.get('started_at'))} · label policy: {_e(analysis['meta']['label_policy'])}</div>"]
    if "automated pilot" in meta["label_policy"]:
        parts.append("<div class='banner'><b>Automated pilot.</b> Candidate labels are model or construction proposals awaiting "
                     f"human adjudication. {_population_sentence(pops)} With this few independent task families, rates are "
                     "descriptive only.</div>")
    else:
        parts.append(f"<div class='banner'>{_population_sentence(pops)}</div>")
    if meta.get("population_pooling"):
        mixed = "; ".join(f"{_e(p)}: {_e(', '.join(ts))}" for p, ts in meta["populations"].items())
        parts.append(f"<div class='banner'><b>Populations pooled</b> (<code>--pool-populations</code>). This run mixes "
                     f"{len(meta['populations'])} populations ({mixed}). The summary tables pool them; each population is reported "
                     "separately under “By population” below.</div>")
    if new:
        parts.append(_new_run_summary(analysis))
        rates = ("Pooled rates with (num/den), each distinct graded patch once; the cluster-bootstrap intervals are in the "
                 "appendix. The exact (Clopper-Pearson) interval ignores clustering and is a reference scale only. The macro rate is "
                 "the mean of the per-family rates (primary display above).")
    else:
        rates = ("Pooled rates with (num/den) and the 95% task-family bootstrap interval; * marks a degenerate interval (every "
                 "family has the same rate, so resampling families cannot vary it). The exact (Clopper-Pearson) interval ignores "
                 "clustering and is a reference scale only. The macro rate is the mean of the per-family rates (table below).")
    parts.append(f"<h2>Summary by verifier condition</h2><p class='muted'>Tasks: {analysis['n_tasks']} · task families: "
                 f"{analysis['n_families']} · recorded verification results: {meta['n_results']}. Reference solution and "
                 f"no-op excluded from the rates (sanity table below). {rates}</p><div class='scroll'><table><tr><th>Condition</th>"
                 "<th>False acceptance</th><th>FA exact 95%</th><th>FA macro</th><th>False rejection</th><th>FR exact 95%</th>"
                 "<th>FR macro</th><th>Families with an accepted negative</th><th>Infrastructure outcomes</th>"
                 "<th>Excluded (unlabeled/ambiguous)</th></tr>")
    mac = lambda x: "—" if x.get("macro") is None else f"{x['macro']:.2f}"  # noqa: E731
    for c, d in _ordered(analysis["conditions"]):
        fa, fr = d["false_acceptance"], d["false_rejection"]
        tn = d.get("tasks_with_any_accepted_negative", {"num": 0, "den": 0})
        parts.append(f"<tr><td>{_cname(c)}</td><td>{_rate(fa, not new)}</td><td>{_iv(fa.get('exact95'))}</td><td>{mac(fa)}</td>"
                     f"<td>{_rate(fr, not new)}</td><td>{_iv(fr.get('exact95'))}</td><td>{mac(fr)}</td><td>{tn['num']}/{tn['den']}</td>"
                     f"<td>{d['infrastructure']['num']}/{d['infrastructure']['den']}</td><td>{d['excluded_unlabeled_or_ambiguous']}</td></tr>")
    sanity_head = ("</table></div><h3>Sanity checks</h3><div class='scroll'><table><tr><th>Condition</th><th>Reference passes</th>"
                   "<th>No-op passes</th></tr>")
    if new:  # the per-family table is the primary display above
        parts.append(sanity_head)
    else:
        fams = sorted(analysis.get("per_task", {}))
        parts.append("</table></div><h3>Per-family rates behind the macro rates</h3><div class='scroll'><table><tr><th>Condition</th>"
                     + "".join(f"<th>{_e(t)} FA</th><th>{_e(t)} FR</th>" for t in fams) + "</tr>")
        for c, d in _ordered(analysis["conditions"]):
            pt = d.get("per_task_rates", {})
            cells = "".join("<td>—</td><td>—</td>" if t not in pt else
                            f"<td>{pt[t]['fa_num']}/{pt[t]['fa_den']}</td><td>{pt[t]['fr_num']}/{pt[t]['fr_den']}</td>" for t in fams)
            parts.append(f"<tr><td>{_cname(c)}</td>{cells}</tr>")
        parts.append(sanity_head)
    for c, s in _ordered(analysis["sanity"]):
        r, n = s.get("reference", {}), s.get("noop", {})
        parts.append(f"<tr><td>{_cname(c)}</td><td>{r.get('pass', '-')}/{r.get('n', '-')}</td><td>{n.get('pass', '-')}/{n.get('n', '-')}</td></tr>")
    if new:  # the exact tests are above, the bootstrap intervals in the appendix
        parts.append("</table></div>")
    else:
        parts.append("</table></div><h3>Paired comparisons on the same candidates</h3><p class='muted'>n: labeled candidates for the "
                     "metric (invalid for FA, valid for FR). * marks a degenerate interval (every family has the same difference). "
                     "No comparison is tested for significance.</p><div class='scroll'><table><tr><th>A</th><th>B</th><th>Metric</th>"
                     "<th>A − B</th><th>95% CI</th><th>n</th><th>families</th><th>A accepts, B rejects</th><th>A rejects, B accepts</th></tr>")
        for d in analysis["comparisons"]:
            diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
            ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]" + ("*" if d.get("ci95_degenerate") else "")
            parts.append(f"<tr><td>{_e(d['a'])}</td><td>{_e(d['b'])}</td><td>{d['metric'].upper()}</td><td>{diff}</td><td>{ci}</td>"
                         f"<td>{d.get('n_metric', d['n_common'])}</td><td>{d['n_families']}</td><td>{d['discordant']['a_accepts_b_rejects']}</td>"
                         f"<td>{d['discordant']['a_rejects_b_accepts']}</td></tr>")
        parts.append("</table></div>")
    hv = meta.get("harness_versions", {})
    if hv:
        parts.append("<p class='muted'>Grading harness: " + ", ".join(f"<code>{_e(k)}</code> ({v} results)" for k, v in hv.items()) + "</p>")
    degenerate = "" if new else " * marks a degenerate interval."
    if analysis.get("by_population"):
        parts.append(_group_tables("By population", "Each population on its own rows, with its own task families (reference "
                                   "solution and no-op excluded); the summary tables above pool the populations." + degenerate,
                                   analysis["by_population"], not new))
    if analysis.get("by_stratum"):
        parts.append(_group_tables("By candidate stratum", "<code>task</code> is the task's own candidates (task.json); every other "
                                   "stratum's candidates are listed in <code>tasks/&lt;id&gt;/strata/&lt;name&gt;.json</code> "
                                   "(reference solution and no-op excluded); the summary tables above pool the strata." + degenerate,
                                   analysis["by_stratum"], not new))
    if analysis.get("fresh_attempts"):
        parts.append(_fresh_section(analysis["fresh_attempts"]))
    if analysis.get("source_evidence"):
        parts.append(_source_section(analysis["source_evidence"]))
    if new:
        parts.append(_new_run_sections(analysis))
    sens = analysis.get("sensitivity_construction_labels")
    if sens:
        parts.append("<h3>Exploratory sensitivity: construction-intent labels</h3><p class='muted'>Not pre-specified (protocol v0.3). "
                     "Constructed candidates labeled by how they were built (including those the pre-specified rule marked ambiguous); "
                     "the observed pre-correction state keeps its proposed label.</p><div class='scroll'><table><tr><th>Condition</th>"
                     "<th>False acceptance</th><th>FA exact 95%</th><th>False rejection</th><th>FR exact 95%</th></tr>")
        for c, d in _ordered(sens):
            fa = {'rate': d['fa'], 'num': d['fa_num'], 'den': d['fa_den'], 'ci95': d['fa_ci95'], 'ci95_degenerate': d.get('fa_ci95_degenerate')}
            fr = {'rate': d['fr'], 'num': d['fr_num'], 'den': d['fr_den'], 'ci95': d['fr_ci95'], 'ci95_degenerate': d.get('fr_ci95_degenerate')}
            parts.append(f"<tr><td>{_cname(c)}</td><td>{_rate(fa, not new)}</td><td>{_iv(d.get('fa_exact95'))}</td>"
                         f"<td>{_rate(fr, not new)}</td><td>{_iv(d.get('fr_exact95'))}</td></tr>")
        parts.append("</table></div>")
    if analysis.get("near_miss_crosstab"):
        xt, ck, nd = analysis["near_miss_crosstab"], analysis.get("sensitivity_check_labels", {}), analysis.get("sensitivity_without_duplicates", {})
        parts.append("<h3>Post-hoc analyses after the internal review</h3><p class='muted'>Exploratory, not pre-specified (protocol v0.4). "
                     "Near misses accepted among those the label rule confirmed invalid and among those it marked ambiguous; rates under "
                     "the independent construction checks' labels; rates without the held-out candidates that duplicate a development "
                     "candidate.</p><div class='scroll'><table><tr><th>Condition</th><th>Near misses accepted (confirmed invalid)</th>"
                     "<th>Near misses accepted (ambiguous)</th><th>FA (check labels)</th><th>FR (check labels)</th>"
                     "<th>FA (no duplicates)</th><th>FR (no duplicates)</th></tr>")
        for c, x in _ordered(xt):
            k, n = ck.get(c, {}), nd.get(c, {})
            parts.append(f"<tr><td>{_cname(c)}</td><td>{x['confirmed_invalid']['accepted']}/{x['confirmed_invalid']['n']}</td>"
                         f"<td>{x['ambiguous']['accepted']}/{x['ambiguous']['n']}</td><td>{k.get('fa_num', '—')}/{k.get('fa_den', '—')}</td>"
                         f"<td>{k.get('fr_num', '—')}/{k.get('fr_den', '—')}</td><td>{n.get('fa_num', '—')}/{n.get('fa_den', '—')}</td>"
                         f"<td>{n.get('fr_num', '—')}/{n.get('fr_den', '—')}</td></tr>")
        parts.append("</table></div>")
        if analysis.get("duplicates"):
            parts.append("<p class='muted'>Duplicates: " + "; ".join(
                f"{_e(cid)} ({_e(', '.join(f'{k.replace(chr(95), chr(32))} {v}' for k, v in d.items() if k != 'task_id'))})"
                for cid, d in analysis["duplicates"].items()) + ".</p>")
        b1 = analysis.get("b1_upstream_only")
        if b1:
            parts.append(f"<p class='muted'>B1 scored only on checks from the base commit's own tests: false acceptance "
                         f"{b1['fa_num']}/{b1['fa_den']}, false rejection {b1['fr_num']}/{b1['fr_den']}. Under the label rule a valid "
                         "candidate must pass these tests, so this variant cannot reject a valid candidate.</p>")
    labels = analysis.get("labels")
    if labels:
        parts.append("<h3>Labels and human-review queue</h3><div class='scroll'><table><tr><th>Task</th><th>Valid</th><th>Invalid</th>"
                     "<th>Ambiguous</th><th>Unlabeled</th><th>Queued for human review</th></tr>")
        for t, td in labels.items():
            for name, d in [(t, td)] + [(f"{t} (stratum {st})", sd) for st, sd in td.get("strata", {}).items()]:
                q = "<br>".join(f"{_e(x['candidate'])} <span class='muted'>({_e(x['reason'])})</span>" for x in d["review_queue"]) or "—"
                cn = d["counts"]
                parts.append(f"<tr><td>{_e(name)}</td><td>{cn.get('valid', 0)}</td><td>{cn.get('invalid', 0)}</td>"
                             f"<td>{cn.get('ambiguous', 0)}</td><td>{cn.get('unlabeled', 0)}</td><td>{q}</td></tr>")
        parts.append("</table></div>")
    cov = analysis.get("coverage")
    if cov:
        parts.append("<h3>Contract recovery against the reference contract</h3><p class='muted'>Model mappings (proposals). Coverage counts "
                     "active scored reference requirements that a recovered requirement maps to without contradicting. Covered but "
                     "contradicted: covered by one recovered requirement and contradicted by another (reported, not subtracted).</p>"
                     "<div class='scroll'><table><tr><th>Task</th><th>Variant</th><th>Coverage (mapper 1)</th><th>Missing</th>"
                     "<th>Covered but contradicted</th><th>Unsupported</th>"
                     "<th>Contradicting</th><th>Coverage (mapper 2)</th><th>Mapper agreement κ</th></tr>")
        for t, cv in cov.items():
            ag = analysis.get("mapping_agreement", {}).get(t, {})
            for v, d in cv.get("variants", {}).items():
                d2 = cv.get("variants_mapper2", {}).get(v)
                k = ag.get(v, {}).get("kappa")
                n_ref = len(cv.get("reference_scored", []))
                c2 = f"{d2['coverage']:.2f} ({len(d2['covered'])}/{n_ref})" if d2 and d2.get("coverage") is not None else "—"
                parts.append(f"<tr><td>{_e(t)}</td><td>{_e(v)}</td><td>{d['coverage']:.2f} ({len(d['covered'])}/{n_ref})</td>"
                             f"<td>{_e(', '.join(d['missing'])) or '—'}</td><td>{_e(', '.join(d.get('covered_but_contradicted', []))) or '—'}</td>"
                             f"<td>{len(d['unsupported'])}/{d['n_recovered_scored']}</td>"
                             f"<td>{_e(', '.join(d['contradicting'])) or '—'}</td><td>{c2}</td><td>{'—' if k is None else f'{k:.2f}'}</td></tr>")
        parts.append("</table></div>")

    by_task: dict[str, list[VerificationResult]] = {}
    for r in results:
        by_task.setdefault(r.task_id, []).append(r)
    for t in manifest["tasks"]:
        tid = t["task_id"]
        tdir = tasks_root / tid
        m = load(tdir / "task.json", TaskManifest)
        parts.append(f"<h2>Task {_e(tid)}</h2><div class='muted'>population <span class='tag'>{_e(m.population.value)}</span> family "
                     f"<span class='tag'>{_e(m.family_id)}</span> source <code>{_e(m.snapshot_source.repo_url)}</code> @ "
                     f"<code>{_e(m.snapshot_source.commit[:12])}</code> · status {_e(m.status)}</div>")
        try:
            session = session_for_task(tdir, repo_root)
            parts.append("<h3>User turns in the source session</h3>")
            for ev in session.user_prompts():
                parts.append(f"<div class='turn'><span class='tag'>{_e(ev.event_id)}</span> <span class='tag'>{_e(ev.author.value)}</span>\n{_e(ev.text)}</div>")
        except FileNotFoundError:
            parts.append("<p class='muted'>Transcript not available.</p>")
        parts.append("<h3>Contracts</h3><div class='scroll'><table><tr><th>Variant</th><th>Requirement</th><th>Kind</th><th>Status</th><th>Statement</th><th>Evidence</th></tr>")
        for variant in ("initial_only", "full_session", "reference"):
            p = m.contracts.get(variant)
            if not p or not (tdir / p).exists():
                continue
            c = load(tdir / p, TaskContract)
            for rq in c.requirements:
                ev = "; ".join(f"“{_e(s.quote)}”" for s in rq.evidence) or _e(rq.rationale)
                parts.append(f"<tr><td>{_e(variant)}</td><td>{_e(rq.req_id)}</td><td>{_e(rq.kind.value)}</td><td>{_e(rq.status.value)}</td>"
                             f"<td>{_e(rq.statement)}</td><td>{ev}</td></tr>")
        parts.append("</table></div>")
        cands = {load(tdir / p, Candidate).candidate_id: load(tdir / p, Candidate) for p in m.candidates}
        stratum = {cid: name for cid, (name, _, _) in strata_of[tid].items()}  # stratum candidates, as the run recorded them
        cands.update({cid: c for cid, (_, _, c) in strata_of[tid].items()})
        specs = {load(tdir / p, VerifierSpec).verifier_id: load(tdir / p, VerifierSpec) for p in m.verifiers}
        rs = by_task.get(tid, [])
        vids = [v for v in t["verifiers"]]
        cids = sorted({r.candidate_id for r in rs})
        grid = {(r.verifier_id, r.candidate_id): r for r in rs}
        parts.append("<h3>Outcome matrix (verifier × held-out candidate)</h3><div class='scroll'><table><tr><th>Candidate</th>"
                     + ("<th>Stratum</th>" if with_strata else "") + "<th>Origin</th><th>Label</th>"
                     + "".join(f"<th>{_e(v)}</th>" for v in vids) + "</tr>")
        for cid in cids:
            c = cands[cid]
            lb = _label(c, analysis)
            excluded = attempt_exclusion(c)
            lab = (f"excluded <span class='muted'>({_e(excluded)})</span>" if excluded
                   else f"{_e(lb.value)} <span class='muted'>({_e(lb.labeler_kind.value)})</span>" if lb
                   else "needs adjudication" if c.human_disagreement() else "—")
            cells = []
            for v in vids:
                r = grid.get((v, cid))
                if r is None:
                    cells.append("<td>—</td>")
                    continue
                failed = [k.check_id for k in r.checks if k.status != "passed"]
                tip = _e("; ".join(failed[:8]) + (" …" if len(failed) > 8 else ""))
                cells.append(f"<td><span class='{_cls(r.outcome.value)}' title='{tip}'>{_e(r.outcome.value)}</span>"
                             f"{'<br><span class=muted>' + str(len(failed)) + ' failing</span>' if failed else ''}</td>")
            strat = f"<td>{_e(stratum.get(cid, 'task'))}</td>" if with_strata else ""
            parts.append(f"<tr><td>{_e(cid)}</td>{strat}<td>{_e(c.origin.value)}</td><td>{lab}</td>{''.join(cells)}</tr>")
        parts.append("</table></div>")
        parts.append("<h3>Candidates</h3>")
        for cid in cids:
            c = cands[cid]
            lb = _label(c, analysis)
            viol = ", ".join(lb.violated_requirements) if lb and lb.violated_requirements else ""
            parts.append(f"<details><summary><b>{_e(cid)}</b> · {_e(c.origin.value)}"
                         f"{(' · stratum ' + _e(stratum[cid])) if cid in stratum else ''} · {_e(c.split.value)} · "
                         f"{_e(lb.value if lb else 'needs adjudication' if c.human_disagreement() else 'unlabeled')}"
                         f"{(' · violates ' + _e(viol)) if viol else ''} — {_e(c.description)}</summary>"
                         f"<pre>{_e(c.patch[:20000])}</pre></details>")
        parts.append("<h3>Verifiers</h3><div class='scroll'><table><tr><th>Verifier</th><th>Condition</th><th>Isolation</th><th>Checks</th><th>Frozen</th><th>Audit</th></tr>")
        for vid, s in specs.items():
            aud = f"{'passed' if s.audit.passed else 'not passed'} after {s.audit.iterations} iteration(s)" if s.audit else "—"
            parts.append(f"<tr><td>{_e(vid)}</td><td>{_e(s.condition.value)}</td><td>{_e(s.isolation.value)}</td><td>{len(s.checks)}</td>"
                         f"<td>{s.frozen}</td><td>{_e(aud)}</td></tr>")
        parts.append("</table></div><h3>Diagnostics</h3>")
        for r in rs:
            if r.diagnostics or r.outcome.value not in ("pass", "task_failure"):
                parts.append(f"<details><summary>{_e(r.verifier_id)} × {_e(r.candidate_id)}: <span class='{_cls(r.outcome.value)}'>{_e(r.outcome.value)}</span></summary>"
                             f"<pre>{_e(chr(10).join(r.diagnostics))}</pre></details>")
    if new:
        parts.append(_bootstrap_appendix(analysis))
    parts.append(_licence_notices(manifest, tasks_root, repo_root))
    parts.append("<p class='muted'>Generated by tracecontract.report from recorded runs only.</p></main></body></html>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
