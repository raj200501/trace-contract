"""Static, self-contained HTML report built only from recorded artifacts.

``build_report(run_dir, tasks_root, repo_root, out)`` renders, for every task in a
run: the user turns of the source session, the requirement contracts side by side
(initial-only, correction-aware, reference), every evaluated candidate with its
label and patch, and the verifier x candidate outcome matrix with failing checks
and diagnostics. Numbers come from ``analysis.json``; nothing is typed in by hand.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .schemas import Candidate, TaskContract, TaskManifest, VerificationResult, VerifierSpec
from .store import load, read_jsonl

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


def _e(s) -> str:
    return html.escape("" if s is None else str(s))


def _cls(outcome: str) -> str:
    return "pass" if outcome == "pass" else "fail" if outcome == "task_failure" else "infra"


def _rate(d: dict) -> str:
    if d.get("rate") is None:
        return f"n/a (0/{d.get('den', 0)})"
    s = f"{d['rate']:.2f} ({d['num']}/{d['den']})"
    if d.get("ci95"):
        s += f" [{d['ci95'][0]:.2f}, {d['ci95'][1]:.2f}]"
    return s


def build_report(run_dir: Path, tasks_root: Path, repo_root: Path, out: Path) -> Path:
    from .tasks import session_for_task

    analysis = json.loads((run_dir / "analysis.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    results = read_jsonl(run_dir / "results.jsonl", VerificationResult)
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>TraceContract Run Report</title><style>{CSS}</style></head><body><main>",
             f"<h1>TraceContract run report</h1><div class='muted'>run <code>{_e(manifest['run_id'])}</code> · code {_e(manifest.get('code_revision'))} · "
             f"started {_e(manifest.get('started_at'))} · label policy: {_e(analysis['meta']['label_policy'])}</div>"]
    if "automated pilot" in analysis["meta"]["label_policy"]:
        parts.append("<div class='banner'><b>Automated pilot.</b> Candidate labels are model or construction proposals awaiting "
                     "human adjudication. Sessions are <b>controlled</b> (real agent runs with scripted user turns), not natural "
                     "user traffic. With this few independent task families, rates are descriptive only.</div>")
    parts.append(f"<h2>Summary by verifier condition</h2><p class='muted'>Tasks: {analysis['n_tasks']} · task families: "
                 f"{analysis['n_families']} · recorded verification results: {analysis['meta']['n_results']}. Reference solution and "
                 "no-op excluded from the rates (sanity table below).</p><div class='scroll'><table><tr><th>Condition</th><th>False acceptance</th>"
                 "<th>False rejection</th><th>Infrastructure outcomes</th><th>Excluded (unlabeled/ambiguous)</th></tr>")
    for c, d in analysis["conditions"].items():
        parts.append(f"<tr><td>{_e(c)}</td><td>{_rate(d['false_acceptance'])}</td><td>{_rate(d['false_rejection'])}</td>"
                     f"<td>{d['infrastructure']['num']}/{d['infrastructure']['den']}</td><td>{d['excluded_unlabeled_or_ambiguous']}</td></tr>")
    parts.append("</table></div><h3>Sanity checks</h3><div class='scroll'><table><tr><th>Condition</th><th>Reference passes</th><th>No-op passes</th></tr>")
    for c, s in analysis["sanity"].items():
        r, n = s.get("reference", {}), s.get("noop", {})
        parts.append(f"<tr><td>{_e(c)}</td><td>{r.get('pass', '-')}/{r.get('n', '-')}</td><td>{n.get('pass', '-')}/{n.get('n', '-')}</td></tr>")
    parts.append("</table></div><h3>Paired comparisons on the same candidates</h3><div class='scroll'><table><tr><th>A</th><th>B</th><th>Metric</th>"
                 "<th>A − B</th><th>95% CI</th><th>n</th><th>families</th><th>A accepts, B rejects</th><th>A rejects, B accepts</th></tr>")
    for d in analysis["comparisons"]:
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]"
        parts.append(f"<tr><td>{_e(d['a'])}</td><td>{_e(d['b'])}</td><td>{d['metric'].upper()}</td><td>{diff}</td><td>{ci}</td>"
                     f"<td>{d['n_common']}</td><td>{d['n_families']}</td><td>{d['discordant']['a_accepts_b_rejects']}</td>"
                     f"<td>{d['discordant']['a_rejects_b_accepts']}</td></tr>")
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
        specs = {load(tdir / p, VerifierSpec).verifier_id: load(tdir / p, VerifierSpec) for p in m.verifiers}
        rs = by_task.get(tid, [])
        vids = [v for v in t["verifiers"]]
        cids = sorted({r.candidate_id for r in rs})
        grid = {(r.verifier_id, r.candidate_id): r for r in rs}
        parts.append("<h3>Outcome matrix (verifier × held-out candidate)</h3><div class='scroll'><table><tr><th>Candidate</th><th>Origin</th><th>Label</th>"
                     + "".join(f"<th>{_e(v)}</th>" for v in vids) + "</tr>")
        for cid in cids:
            c = cands[cid]
            lb = c.final_label() or c.proposed_label()
            lab = f"{_e(lb.value)} <span class='muted'>({_e(lb.labeler_kind.value)})</span>" if lb else "—"
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
            parts.append(f"<tr><td>{_e(cid)}</td><td>{_e(c.origin.value)}</td><td>{lab}</td>{''.join(cells)}</tr>")
        parts.append("</table></div>")
        parts.append("<h3>Candidates</h3>")
        for cid in cids:
            c = cands[cid]
            lb = c.final_label() or c.proposed_label()
            viol = ", ".join(lb.violated_requirements) if lb and lb.violated_requirements else ""
            parts.append(f"<details><summary><b>{_e(cid)}</b> · {_e(c.origin.value)} · {_e(c.split.value)} · "
                         f"{_e(lb.value if lb else 'unlabeled')}{(' · violates ' + _e(viol)) if viol else ''} — {_e(c.description)}</summary>"
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
    parts.append("<p class='muted'>Generated by tracecontract.report from recorded runs only.</p></main></body></html>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
