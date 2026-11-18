# TraceContract

**Do the verifiers of trace-derived coding tasks reward what the user actually
wanted?** When a coding task is reconstructed from an agent session, later user
corrections change what counts as a correct solution, for example "actually, keep
the old default" or "step=0 must raise". A verifier built from an incomplete
account of those corrections can go wrong in two ways:

* **false acceptance:** it accepts solutions the user rejected;
* **false rejection:** it rejects solutions the user would accept.

TraceContract measures both directly.

> **Status: research prototype, automated pilot only.**
> * No human labels exist yet; candidate labels are proposals from a pre-specified rule.
> * All four sessions are *controlled*: real agent runs with user turns scripted by
>   the study, not natural user traffic.
> * Nothing here is peer reviewed.
>
> See [STATUS.md](STATUS.md).

## What is here

* **A measurement design.** Every verifier condition scores the *same* held-out
  candidate patches. Each task's pool holds:
  * the agent's naturally observed **pre-correction state**;
  * constructed near misses;
  * independent valid alternatives.

  The pool is generated only after the verifiers are frozen. The conditions form a
  2×2 grid:

  | | plain generated tests | + predefined audit (audit:v1) |
  | --- | --- | --- |
  | initial-request-only contract | C1 `initial_plain` | C2 `initial_audited` |
  | correction-aware contract | C3 `full_plain` | C4 `full_audited` |

  There are two baselines: B1 (repository tests at the reference state) and B2 (an
  LLM given the whole session, without contract machinery). The initial-only arm
  measures information lost during dataset construction, not agent capability.
* **Evidence-linked contracts.**
  * Each requirement carries exact quotes from the session, a status (explicit,
    inferred, superseded or unresolved) and the turn that introduced it.
  * Superseded requirements are never scored.
  * Inferred requirements need human review before a task is accepted
    (`src/tracecontract/contract.py`).
* **Process-separated grading (harness `tc-harness/0.3.0`).**
  * Hidden tests run in a trusted grader.
  * Candidate code runs only as an unprivileged UID allocated to that container. It
    cannot read the tests or write the results.
  * Per-call results are authenticated, and the host recomputes outcomes, so a
    missing or stale result never becomes a reward.
  * Adversarial Docker probes cover the boundary (`tests/test_sandbox_isolation.py`).
    They include regression probes for the two resource-isolation defects found
    during the pilot (decision log D29–D31).
* **Controlled-session protocol (CS-v1):** pre-registered scenarios, state capture
  between turns, transcript sanitisation and contamination audits.
* **Labels, checks and review.**
  * Label proposals come from a pre-specified rule (D19): independent reference
    checks, plus the regression norm, plus construction intent. Disagreement gives
    `ambiguous`.
  * An independent model check of every held-out candidate
    (`tasks/*/labels/construction_checks.json`) is advisory only.
  * A human-review queue that shows no verifier outcomes is in
    `tasks/*/labels/review_queue.json`.
* **Harbor export** (pinned 0.25.0, separate verifier, only approved artifacts).

Related work: [docs/research_brief.md](docs/research_brief.md), adversarially
verified, and `paper/sections/related.tex`. Each component of the design has
partial precedents, notably SessionFarmer, SWE-Together and Trace2Eval. The claim
is limited to their *combination*: initial-only vs correction-aware verifiers from
one frozen procedure, scored on one frozen held-out pool anchored on the session's
own pre-correction states, against independent human labels (decision log D34). The
last element does not exist yet.

## Pilot results (automated labels, four controlled task families)

Run `results/runs/pilot-v0.3`:
* 4 tasks × 6 conditions × 10 candidates = 240 graded pairs;
* harness 0.3.0, one code revision;
* no infrastructure outcomes.

Of the 32 held-out candidates, 17 are labeled invalid, 10 valid and 5 ambiguous
(excluded). The report is `results/runs/pilot-v0.3/report.html`; the analysis is
`results/runs/pilot-v0.3/analysis.md`.

| Condition | False acceptance | False rejection |
| --- | --- | --- |
| C1 initial-only, plain | 6/17 | 2/10 |
| C2 initial-only, audited | 5/17 | 2/10 |
| C3 correction-aware, plain | 0/17 | 0/10 |
| C4 correction-aware, audited | 0/17 | 0/10 |
| B2 full-session LLM | 1/17 | 0/10 |
| B1 repository tests (reference state) | 5/17 | 4/10 |

How to read this:

* **Initial-only verifiers reward what the correction ruled out.**
  * Every invalid candidate they accept violates a correction-introduced
    requirement.
  * They accept both pre-correction states that are labeled invalid.
  * In `humanize`, where the correction retracted the initial request, they reject
    both valid alternatives and the reference solution.
* **The effect depends on the session and on the contract proposer.**
  * In `tinydb` the proposer inferred the correction's requirements from the first
    request alone.
  * In `inflection` and `tinydb` the agent's own pre-correction state already
    satisfied the correction.
* **The audit changed one outcome out of 64.** It cannot repair a verifier whose
  contract is wrong.
* **Repository tests fail in both directions.** They miss the correction's
  invariants and over-specify the reference implementation.
* **Selection effect.** The ambiguous near misses are the hard cases. When they are
  labeled by construction intent (exploratory, not pre-specified), the
  correction-aware verifiers accept 3 of 22 invalid candidates.
* **Uncertainty.** Intervals over four families are wide. Eight candidates are
  queued for human review, five of them because the rule marked them ambiguous.
  **These are descriptive pilot numbers, not evidence of an effect.**

## Demonstration (CS-01, controlled)

1. *Initial request:* make `humanize.naturalsize` drop a trailing ".0" ("3 MB"
   instead of "3.0 MB").
2. The agent changes the default output.
3. *Correction:* keep the default output exactly as before, and make trimming
   opt-in via `strip_trailing_zero`. Custom formats, even positional ones, must not
   change.

The agent's state after step 2 is a natural negative: it satisfies the initial
request but violates the correction.
* In run `pilot-v0.3`, both initial-only verifiers (C1, C2) accept it, and reject
  both valid alternatives and the reference solution.
* All correction-aware conditions reject it and accept the alternatives.

## Reproduce

Requirements: Linux, Python ≥ 3.12, Docker (daemon running) and `git`. Grading
needs no network; building images needs PyPI access from the host.

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
.venv/bin/python scripts/preflight_final_run.py tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04
```

```bash
.venv/bin/tracecontract evaluate tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04 --run-id my-run --conditions initial_plain initial_audited full_plain full_audited llm_freeform repo_tests
```

```bash
.venv/bin/tracecontract analyze results/runs/my-run --allow-proposed-labels
```

```bash
.venv/bin/tracecontract report results/runs/my-run --out results/runs/my-run/report.html
```

```bash
.venv/bin/python scripts/compare_runs.py results/runs/pilot-v0.3 results/runs/my-run
```

```bash
.venv/bin/python paper/make_tables.py results/runs/pilot-v0.3 --compare results/runs/pilot-v0.2 results/runs/pilot-v0.2-h2
```

```bash
cd paper && latexmk -pdf main.tex
```

Model-generated artifacts (sessions, contracts, tests, candidates, label proposals,
checks and mappings) are recorded in the repository. Regenerating them is not
bit-reproducible. Everything downstream of them is: grading, analysis, tables,
report and paper numbers. `paper/evidence_ledger.md` lists the source of every
number in the generated tables.

## Limitations

* No human labels. The labels are rule-based proposals, and an independent model
  check disputes some of them.
* Controlled sessions only, with scripted corrections designed by the study.
* One model family produced the sessions, contracts, verifiers, candidates, label
  proposals, checks and both requirement mappers.
* Four task families, so all rates are descriptive.
* Repository-test baseline (B1): it imports candidate code into its reporting
  process, so an adversarial candidate can forge its report. A characterisation
  probe in the test suite shows this.
* Natural data (SWE-chat) is blocked on dataset access terms.

## Layout

```
src/tracecontract/   schemas, ingest, contract, snapshot, patches, sandbox/, verifier, audit,
                     evaluate, metrics, analysis, report, harbor_export, controlled, tasks, cli
tasks/<id>/          task manifests, provenance, contracts (+ mappings), candidates, verifiers, labels
data/                manifests, sanitised controlled transcripts, scenarios, reference proposals
experiments/         protocol.md (v0.3)
results/runs/<id>/   manifest, raw results, analysis, comparisons, report
scripts/             label proposals, construction checks, review queues, preflight, run comparison
docs/                research brief, decision log, data card, annotation guide, status docs
paper/               LaTeX draft, verified bibliography, table generator, evidence ledger
```

Licence: not yet chosen by the repository owner.
