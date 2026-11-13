# TraceContract

**Do the verifiers of trace-derived coding tasks reward what the user actually
wanted?** When a coding task is reconstructed from an agent session, later user
corrections ("actually, keep the old default", "step=0 must raise") change what a
correct solution is. A verifier built from an incomplete account of those
corrections can accept solutions the user rejected (false acceptance) or reject
solutions the user would accept (false rejection). TraceContract measures this
directly.

> **Status: research prototype, automated pilot only.** No human labels exist yet;
> all sessions so far are *controlled* (real agent runs with scripted user turns),
> not natural user traffic. Nothing here is peer reviewed. See [STATUS.md](STATUS.md).

## What is here

* **A measurement design.** The *same* held-out candidate patches — including the
  agent's naturally observed **pre-correction state**, constructed near misses, and
  independent valid alternatives — are scored by every verifier condition and
  compared with independent labels:

  | | plain generated tests | + predefined audit (audit:v1) |
  | --- | --- | --- |
  | initial-request-only contract | C1 `initial_plain` | C2 `initial_audited` |
  | correction-aware contract | C3 `full_plain` | C4 `full_audited` |

  plus B1 (repository tests at the reference state) and B2 (an LLM given the whole
  session, without contract machinery). The initial-only arm measures information
  lost during dataset construction, not agent capability.
* **Evidence-linked contracts.** Requirements carry exact quotes into the session,
  a status (explicit / inferred / superseded / unresolved) and the turn that
  introduced them; superseded requirements are never scored; inferred ones need
  human review before a task is accepted (`src/tracecontract/contract.py`).
* **Process-separated grading.** Hidden tests run in a trusted grader; candidate
  code runs only as an unprivileged user that cannot read the tests or write the
  results; per-call results are authenticated; the host recomputes outcomes, so
  missing or stale results never become rewards. The boundary is covered by
  adversarial integration tests (`tests/test_sandbox_isolation.py`).
* **Controlled-session protocol (CS-v1)** with pre-registered scenarios, state
  capture between turns, transcript sanitisation and contamination audits.
* **Harbor export** (pinned 0.25.0, separate verifier, only approved artifacts).

Related work and positioning: [docs/research_brief.md](docs/research_brief.md).
Closest prior work reconstructs tasks from sessions and preserves later
requirements (e.g. SWE-Together, Trace2Eval); this project's claim is limited to
*measuring* verifier reward fidelity against independent labels.

## Demonstration (CS-01, controlled)

1. *Initial request:* make `humanize.naturalsize` drop a trailing ".0"
   ("3 MB" instead of "3.0 MB").
2. The agent changes the default output.
3. *Correction:* keep the default output exactly as before; make trimming opt-in via
   `strip_trailing_zero`; custom formats (even positional) must not change.

The agent's state after step 2 is a natural negative: it satisfies the initial
request but violates the correction. An initial-request verifier rewards it and
rejects the final solution; see the run report for what each verifier did.
`RESULTS_PLACEHOLDER`

## Reproduce

Requirements: Linux, Python ≥ 3.12, Docker (daemon running), `git`. No network is
needed at grading time; building images needs PyPI access from the host.

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -e ".[dev,data]"
```

```bash
.venv/bin/python -m pytest -q -m "not docker"   # offline unit/pipeline tests (fixtures only)
```

```bash
.venv/bin/python -m pytest -q -m docker          # grading-isolation probes (needs Docker)
```

```bash
.venv/bin/tracecontract snapshot tasks/CS-01     # rebuild a base snapshot from its pinned commit
```

```bash
.venv/bin/tracecontract validate-task tasks/CS-01
```

```bash
.venv/bin/tracecontract grade tasks/CS-01 full_audited CS-01-pre-correction
```

```bash
.venv/bin/tracecontract evaluate tasks/CS-01 --run-id my-run
```

```bash
.venv/bin/tracecontract analyze results/runs/my-run --allow-proposed-labels
```

```bash
.venv/bin/tracecontract report results/runs/my-run --out results/runs/my-run/report.html
```

```bash
cd paper && latexmk -pdf main.tex
```

Model-generated artifacts (sessions, contracts, tests, candidates) are recorded in
the repository; regenerating them is not bit-reproducible. Everything downstream of
them (grading, analysis, tables, report, paper numbers) is.

## Limitations

* Controlled sessions only; scripted corrections designed by the study.
* One model family produced the sessions, contracts, verifiers, candidates and
  label proposals.
* Labels are proposals until human review (`docs/annotation_guide.md`).
* Four task families: rates are descriptive; intervals are not evidence of effects.
* Natural data (SWE-chat) is blocked on dataset access terms.

## Layout

```
src/tracecontract/   schemas, ingest, contract, snapshot, patches, sandbox/, verifier, audit,
                     evaluate, metrics, analysis, report, harbor_export, controlled, tasks, cli
tasks/<id>/          task manifests, provenance, contracts, candidates, verifiers
data/                manifests, sanitised controlled transcripts, scenarios
experiments/         protocol.md
results/runs/<id>/   manifest, raw results, analysis, report
docs/                research brief, decision log, data card, annotation guide, status docs
paper/               LaTeX draft, verified bibliography, table generator, evidence ledger
```

Licence: not yet chosen by the repository owner.
