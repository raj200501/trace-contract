# Ownership and defense

This document separates what the repository borrows, what was produced with AI
assistance, and what only the human author(s) can contribute. It does not claim
any personal contribution on anyone's behalf; the "human decisions" section lists
decisions that are still open or that must be reviewed.

## Borrowed components (with licences)

| Component | Use | Licence |
| --- | --- | --- |
| Harbor 0.25.0 (PyPI `harbor`) | Task-package format and local oracle/no-op validation of exported tasks | Apache-2.0 |
| pytest 9.2.0, hypothesis 6.131.0 and their dependencies | Test runner inside grading containers | MIT/MPL-2.0 (see wheel metadata) |
| pydantic 2 | Typed schemas | MIT |
| `python:3.12-slim` image (pinned digest) | Base image for sandboxes | PSF/Debian licences |
| Source repositories of the controlled tasks (humanize, tinydb, inflection, more-itertools) | Base snapshots and candidate patches | MIT (each repository's licence) |
| Ideas: oracle/no-op checks, cheat trials and hacker/fixer loops (Terminal-Bench task review); FAIL_TO_PASS/PASS_TO_PASS selection (SWE-bench family); separate verifier and artifact transfer (Harbor) | Design of audit:v1 and baseline B1 | cited in the research brief |

## AI-assisted work (substantial)

Produced with Claude (via Claude Code), reviewed only by the model so far:

* all package code, tests, scripts, CLI, report and Harbor exporter;
* the research notes and research brief (multi-agent literature review), the
  decision log, protocol v0.1, annotation guide, data card and the manuscript draft;
* the controlled sessions themselves (the coding agent is a Claude model), the
  recovered contracts, all generated verifiers, development attacks, valid
  alternatives, near misses, reference checks, and every proposed label.

## Human decisions and reviews still required

1. **Contract review and candidate labels** for every task
   (`docs/annotation_guide.md`), plus a second reviewer on an overlap subset.
2. **Data access**: accept the SWE-chat terms and supply a working read token, or
   decide on another natural-data source.
3. **Scope of the claim** after reading the adversarial novelty review (SWE-Together
   and Trace2Eval are the closest work).
4. **Repository licence** and the licence of released task data.
5. **Authorship, AI-use disclosure, and whether/when to submit anything.**
6. **Spending**: whether to approve any paid model or compute budget (default zero),
   e.g. for a second model family or fresh-agent difficulty checks.

## Ten hard technical questions (be ready to answer these yourself)

1. Why does the initial-request-only baseline measure *information lost during
   dataset construction* rather than agent capability, and what would be a fair
   agent-side comparison instead?
2. In process-separated grading, what exactly can a malicious candidate still do?
   Why must tests assert on concrete values rather than on `r.ok`? What does the
   per-call HMAC detect, and what can it not prevent?
3. Why are missing, stale, or unparseable results `verifier_error` rather than
   reward 0, and how does Harbor 0.25.0 represent the same situations?
4. Why is the reference solution excluded from false-rejection rates, and why is the
   audit allowed to use it?
5. How can the audit of an *initial-only* verifier partially recover lost
   information (hint: the reference solution embodies the correction)? Is that a
   flaw of the design or a finding?
6. What makes `observed_pre_correction` a *natural* negative, and when is it not a
   negative at all (see CS-03)? Why must its label come from review, not origin?
7. Why is the task family, not the candidate, the unit of analysis? What happens to
   confidence intervals with four families?
8. Where can leakage enter (reference contract, eval candidates, hidden tests,
   transcripts), and which control addresses each (sealing, freezing order,
   isolated workspaces, access audits)?
9. Why does using one model family for sessions, verifiers, candidates and label
   proposals threaten validity, and what would you change first with a budget?
10. Which parts of this project are genuinely new relative to SWE-Together and
    Trace2Eval, and which conclusions survive if the correction-aware improvement is
    zero?

## Exercises to understand and modify the core system

1. Run `pytest -q -m "not docker"` and then `pytest -q -m docker`; read
   `tests/test_sandbox_isolation.py` and add a probe that tries to modify `/work`
   between two `run_python` calls. Decide whether the result is a vulnerability.
2. Take `tasks/CS-01`, render the session (`tracecontract render-session`), write
   your own reference contract by hand, and compare it with `contracts/full_session.json`.
3. Write a new near-miss candidate for CS-01 by hand, register it with
   `tracecontract add-candidate`, and grade it with every verifier
   (`tracecontract grade`). Which verifiers accept it, and why?
4. Change audit:v1 to require that each development attack fails a check mapped to
   its targeted requirement (currently only reported), rerun the audit, and observe
   the effect.
5. Replace B2's prompt with the SecureForge-style full-session reconstruction
   prompt described in the research notes and compare.
6. Export a task to Harbor (`src/tracecontract/harbor_export.py`), run the oracle
   with two different `CANDIDATE` values, and check that Harbor's reward matches
   `tracecontract grade`.
