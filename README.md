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
>   the study's AI agent, not natural user traffic.
> * Nothing here is peer reviewed.
>
> See [STATUS.md](STATUS.md).

## What is here

* **A measurement design.** Every verifier condition scores the *same* held-out
  candidate patches. Each task's pool holds:
  * the agent's naturally observed **pre-correction state**;
  * constructed near misses;
  * independent valid alternatives.

  The pre-correction state is captured during the session. It existed before the
  verifiers, and its edits appear, abbreviated, in the session text that B2's
  generator and the full-session contract proposer read. The alternatives and near
  misses are generated only after the task's verifiers are frozen (CS-04's B1 was
  re-selected afterwards, decision log D31). The conditions form a 2×2 grid:

  | | plain generated tests | + predefined audit (audit:v1) |
  | --- | --- | --- |
  | initial-request-only contract | C1 `initial_plain` | C2 `initial_audited` |
  | correction-aware contract | C3 `full_plain` | C4 `full_audited` |

  There are two baselines: B1 (repository tests at the reference state) and B2 (an
  LLM given the whole session, without contract machinery). The initial-only arm
  measures information lost during dataset construction, not agent capability.
* **Evidence-linked contracts.**
  * Each requirement carries a status (explicit, inferred, superseded or
    unresolved) and the turn that introduced it; explicit requirements carry exact
    quotes from the session.
  * Superseded requirements are never scored.
  * Inferred requirements need human review before a task is accepted
    (`src/tracecontract/contract.py`).
* **Process-separated grading (harness `tc-harness/0.3.3`)** for C1–C4 and B2.
  * Hidden tests run in a trusted grader.
  * Candidate code runs only as an unprivileged UID allocated to that container. It
    cannot read the tests or write the results.
  * Per-call results are authenticated, and the host recomputes outcomes, so a
    missing or stale result never becomes a reward.
  * **In-call limit:** within one call, code that the snippet runs, directly or
    through candidate modules it imports, still controls what that call reports. It
    can, for example, detect that it is being graded. Every test of these verifiers
    therefore asserts on a returned value, not only on success; the test lint flags
    any test whose only assertions are on success (decision log D3, D36, D40).
  * Adversarial Docker probes cover the boundary (`tests/test_sandbox_isolation.py`).
    They include regression probes for the defects found during the pilot and its
    reviews: two in resource isolation (decision log D29–D31) and two start-up paths
    for forged results, a module shadowing the standard library (D36) and an
    `encodings` package loaded while the interpreter starts (D40).
  * A later verification by model agents found a further path for forged results in
    0.3.2: a candidate `ast.py` could load while the wrapper formatted a snippet's
    exception. Harness 0.3.3 closes it and adds a regression probe for it. No candidate
    patch in the pool ships an `ast` or `unicodedata` module (D44).
  * **Exception:** the repository-test baseline B1 runs pytest with candidate code in
    the reporting process. An adversarial candidate can forge its report (see
    Limitations).
* **Controlled-session protocol (CS-v1):** scenarios hashed and logged locally before
  each run (not a formal preregistration), state capture between turns, transcript
  sanitisation and contamination audits.
* **Labels, checks and review.**
  * Label proposals come from a pre-specified rule (D19): independent reference
    checks, plus the regression norm, plus construction intent. Disagreement gives
    `ambiguous`.
  * An independent model check of every held-out candidate
    (`tasks/*/labels/construction_checks.json`) is advisory only.
  * A human-review queue that shows no verifier outcomes is in
    `tasks/*/labels/review_queue.json`. Reviewers open it only after their labels are
    merged.
  * Human labels are to be made from a blinded review packet (`tracecontract
    review-packet`): the session's user turns, the reference contract, and each
    held-out change under a random id, shuffled, with no proposal or outcome;
    identical changes share one id. The packet hides the origin field but not the
    origin, which the content can reveal: near misses resemble each other and the
    reference, and the user's corrections describe the agent's first attempt. Each
    reviewer therefore records an origin guess per candidate, and the merge reports
    how often the guesses are right. The key stays with a coordinator, and
    `tracecontract merge-reviews` needs two complete reviews per task
    (`docs/annotation_guide.md`, decision log D43, D44).
* **Harbor export** (pinned 0.25.0, separate verifier, only approved artifacts).

Related work: [docs/research_brief.md](docs/research_brief.md), adversarially
verified by model agents (not yet reviewed by a human), and
`paper/sections/related.tex`. Each component of the design has partial precedents,
notably SessionFarmer, SWE-Together and Trace2Eval. The claim is limited to their
*combination*: initial-only vs correction-aware verifiers from one frozen procedure,
scored on one held-out pool anchored on the session's own pre-correction states,
against independent human labels (decision log D34). The last element does not
exist yet, and the pool's departures from blindness are listed under Limitations.

## Pilot results (automated labels, four controlled task families)

Run `results/runs/pilot-v0.3.3`:
* 4 tasks × 6 conditions × 10 candidates = 240 graded pairs;
* harness 0.3.3, one code revision;
* no infrastructure outcomes;
* it agrees with the earlier runs `pilot-v0.3.2` (harness 0.3.2), `pilot-v0.3.1`
  (harness 0.3.1) and `pilot-v0.3` (harness 0.3.0) on all 240 pairs (D45).

Of the 32 held-out candidates, 17 are labeled invalid, 10 valid and 5 ambiguous
(excluded). The report is `results/runs/pilot-v0.3.3/report.html`; the analysis is
`results/runs/pilot-v0.3.3/analysis.md`.

| Condition | False acceptance | False rejection |
| --- | --- | --- |
| C1 initial-only, plain | 6/17 | 2/10 |
| C2 initial-only, audited | 5/17 | 2/10 |
| C3 correction-aware, plain | 0/17 | 0/10 |
| C4 correction-aware, audited | 0/17 | 0/10 |
| B2 full-session LLM | 1/17 | 0/10 |
| B1 repository tests (reference state) | 5/17 | 4/10 |

How to read this:

* **In this pilot, initial-only verifiers rewarded what the correction ruled out.**
  * Every invalid candidate they accept violates a correction-introduced
    requirement. That is largely by construction: 16 of the 17 invalid candidates
    violate one.
  * They accept both pre-correction states that are labeled invalid.
  * In `humanize`, where the correction retracted the initial request, they reject
    both valid alternatives and the reference solution.
* **The size of the gap depends on the session and on the contract proposer.**
  * In `tinydb` the proposer inferred the correction's requirements from the first
    request alone.
  * In `tinydb`, and by the rule's labels in `inflection` (the independent check
    disputes it there), the agent's own pre-correction state already satisfied the
    correction.
* **The audit changed one outcome.** Four of the eight audited verifiers needed no
  revision and are identical to their plain counterparts. On the 32 held-out
  outcomes of the other four, the audit changed one. It cannot repair a verifier
  whose contract is wrong.
* **Repository tests fail in both directions.** They miss the correction's
  invariants and over-specify the reference implementation. B1 includes 6–12 tests
  per task that the session agent added, and all four of its false rejections come
  from those tests. Restricted to the base commit's own tests (exploratory), B1
  accepts 13/17 and rejects 0/10; both numbers largely follow from the label rule,
  whose valid label requires passing those tests.
* **Selection effect.** The ambiguous near misses are the hard cases. The exploratory
  views give these false-acceptance counts for the correction-aware verifiers:
  * 3 of 22 invalid candidates when constructed candidates are labeled by
    construction intent;
  * 6 of 25 under the independent construction checks' labels.
* **Duplicates.** Three held-out candidates duplicate a development attack used in
  their family's C4 audit: two `more-itertools` candidates have the same graded patch,
  and one `humanize` near miss differs by one docstring line (decision log D37, D40).
  Without them (exploratory), C1 accepts 4/14 and C3/C4 0/14.
* **Uncertainty.**
  * Cluster-bootstrap intervals over four families are wide. They are degenerate
    (zero width, marked) wherever every family has the same rate or difference, as
    for C3 and C4.
  * Exact binomial intervals are printed next to them; for 0/17 the upper bound is
    0.20.
  * Eight candidates are in the human-review queue, five of them because the rule
    marked them ambiguous.

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
* In run `pilot-v0.3.3`, both initial-only verifiers (C1, C2) accept it, and reject
  both valid alternatives and the reference solution.
* All correction-aware conditions reject it and accept the alternatives.

## Reproduce

Requirements:
* Linux, Python 3.13 (tested; the package needs ≥ 3.12, and if 3.13 is missing
  `uv venv --python 3.13` downloads a managed build, which needs network access),
  [uv](https://docs.astral.sh/uv/), `git`, and Docker with the daemon running;
* network access from the host: github.com to rebuild the base snapshots
  (`tracecontract snapshot` fetches each pinned commit with git), Docker Hub for the
  digest-pinned `python` base image, and PyPI for the package install and the
  wheelhouses. Grading itself needs no network;
* for the paper: a TeX distribution with `latexmk` and `biber`;
* for the Harbor check only: a Harbor 0.25.0 CLI in a separate environment.

The `dev` extra installs `pip` into the venv; image builds call
`<venv python> -m pip download`.

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
for t in CS-01 CS-02 CS-03 CS-04; do .venv/bin/tracecontract snapshot tasks/$t; done   # rebuild every base snapshot from its pinned commit
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
.venv/bin/python scripts/compare_runs.py results/runs/pilot-v0.3.3 results/runs/my-run
```

```bash
.venv/bin/python paper/make_tables.py results/runs/pilot-v0.3.3 --compare results/runs/pilot-v0.3.2 results/runs/pilot-v0.3.1 results/runs/pilot-v0.3 results/runs/pilot-v0.2 results/runs/pilot-v0.2-h2
```

To write one candidate's final file state to a directory without running any code
(reviewers label from the blinded packet and use this only after their labels are
merged):

```bash
.venv/bin/tracecontract materialize tasks/CS-01 CS-01-pre-correction --out /tmp/review-CS-01-pre
```

To re-check the Harbor export on the synthetic fixture task (outputs are recorded in
`results/harbor_validation/`):

```bash
HARBOR=/path/to/harbor scripts/harbor_validate.sh
```

```bash
cd paper && latexmk -pdf main.tex
```

Model-generated artifacts (sessions, contracts, tests, candidates, label proposals,
checks and mappings) are recorded in the repository. The prompts that produced them
are in `experiments/prompts/`, with owner messages and session paths redacted; the
full agent transcripts are not published. Regenerating these artifacts is not
bit-reproducible. From the recorded results, the analysis, tables, evidence ledger,
report and run comparisons regenerate byte for byte (`analysis.json` differs only in
the recorded git revision). Re-grading reproduces outcomes, not bytes: results carry
timestamps and durations, and tests have time limits. `paper/evidence_ledger.md`
lists every number in the generated tables with its source file.

Before each push, `scripts/scan_tracked_files.py --private-markers <file kept outside
the repository>` is run as a manual step, not as a git hook. It checks the
working tree and every file version in the commits the push would send for
credentials, session-local paths, e-mail addresses and the private markers (decision
log D44). Earlier commits, already pushed, still hold material that has since been
removed; STATUS.md lists it.

## Limitations

* No human labels. The labels are rule-based proposals, and an independent model
  check disputes some of them.
* Controlled sessions only, with scripted corrections designed by the study.
* One model family produced the scenarios and reference contracts that define the
  labels (written by the study's AI agent, the same model as the session agent), the
  sessions, contracts, verifiers, candidates, label proposals, checks and both
  requirement mappers.
* Four task families, so all rates are descriptive.
* Repository-test baseline (B1): it imports candidate code into its reporting
  process, so an adversarial candidate can forge its report. A characterisation
  probe in the test suite shows this. B1 also includes tests that the session agent
  wrote.
* The held-out discipline is imperfect, and each departure is disclosed in decision
  log D31, D37, D40, D41 and D44:
  * generators and reference-check writers ran as the same user in the repository
    checkout, so separation rested on instructions and on audits of their tool inputs
    (tool outputs showed held-out file names to some agents);
  * the held-out generators, the reference-check writers and their reviewers shared
    the build session's scratch directory, which also held other agents' working
    files and some material derived from candidates. The first audit treated only its
    sealed subfolders as forbidden. A stricter re-audit, which treats the whole
    directory as forbidden, found no read of forbidden material. Some listings showed
    file names, and one reviewer of CS-02's checks read part of another reviewer's
    test runner, which holds no candidate or other verifier material
    (`strict_reaudit` in `tasks/*/labels/generator_audit.json`);
  * near-miss generators could run B1's tests;
  * three held-out candidates duplicate a development attack;
  * the reference checks were written while the pools were being generated; CS-03's
    were frozen before its pool was registered, and CS-02's were revised mostly after
    its pool was complete;
  * the prompts of 2026-11-18 (CS-01's near misses, and all of CS-02's held-out
    candidates and reference checks) differ from the earlier CS-03/CS-04 prompts,
    which CS-01's alternatives and reference checks also used;
  * CS-04's B1 was re-selected after its pool existed;
  * the hash of each scored check list was added only after the run `pilot-v0.3`.
* Natural data (SWE-chat) is blocked on dataset access terms.

## Layout

```
src/tracecontract/   schemas, ingest, contract, snapshot, patches, sandbox/, verifier, audit,
                     evaluate, metrics, analysis, report, harbor_export, controlled, tasks, cli
tasks/<id>/          task manifests, provenance, contracts (+ mappings), candidates, verifiers, labels
data/                manifests, sanitised controlled transcripts, scenarios, reference proposals
experiments/         protocol.md (v0.6), prompts/ (workflow scripts and agent prompts)
results/runs/<id>/   manifest, raw results, analysis, comparisons, report (logs are local only)
results/harbor_validation/  recorded Harbor validation outputs (fixture task)
scripts/             label proposals, construction checks, review queues, duplicates, preflight, run comparison, publication scan
docs/                research brief, decision log, data card, annotation guide, internal review, status docs
THIRD_PARTY_LICENSES/ licence notices of the redistributed upstream code
paper/               LaTeX draft, verified bibliography, table generator, evidence ledger
```

Licence: not yet chosen by the repository owner.
