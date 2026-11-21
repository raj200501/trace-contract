# Ownership and defense

This document separates what the repository borrows, what was produced with AI
assistance, and what only the human author(s) can contribute. It does not claim
any personal contribution on anyone's behalf; the "human decisions" section lists
decisions that are still open or that must be reviewed.

## Borrowed components (with licences)

| Component | Use | Licence |
| --- | --- | --- |
| Harbor 0.25.0 (PyPI `harbor`) | Task-package format and local oracle/no-op validation of exported tasks | Apache-2.0 |
| attrs 26.1.0 (wheel) | Grading-image dependency: default, CS-01, CS-02 to CS-04 | MIT (License-Expression) |
| freezegun 1.5.5 (wheel) | Grading-image dependency: CS-01 | "Apache-2.0" (License field) |
| hypothesis 6.131.0 (wheel) | Grading-image dependency: default, CS-01, CS-02 to CS-04 | MPL-2.0 (License-Expression) |
| iniconfig 2.3.1 (wheel) | Grading-image dependency: default, CS-01, CS-02 to CS-04 | MIT (License-Expression) |
| packaging 26.3 (wheel) | Grading-image dependency: default, CS-01, CS-02 to CS-04 | Apache-2.0 OR BSD-2-Clause (License-Expression) |
| pluggy 1.7.0 (wheel) | Grading-image dependency: default, CS-01, CS-02 to CS-04 | "MIT" (License field; classifier: OSI Approved :: MIT License) |
| Pygments 2.21.0 (wheel) | Grading-image dependency: CS-01, CS-02 to CS-04 | BSD-2-Clause (License-Expression) |
| pytest 8.3.5 (wheel) | Test runner in the default grading image | "MIT" (License field; classifier: OSI Approved :: MIT License) |
| pytest 9.2.0 (wheel) | Test runner in the CS-01 to CS-04 grading images | MIT (License-Expression) |
| python-dateutil 4.0.0 (wheel) | Grading-image dependency: CS-01 | BSD-3-Clause (License-Expression) |
| sortedcontainers 2.4.0 (wheel) | Grading-image dependency: default, CS-01, CS-02 to CS-04 | "Apache 2.0" (License field; classifier: OSI Approved :: Apache Software License) |
| tzdata 2026.6 (wheel) | Grading-image dependency: CS-01 | "Apache-2.0" (License field) |
| pydantic 2 | Typed schemas | MIT |
| `python:3.12-slim` image (pinned digest) | Base image for sandboxes | PSF/Debian licences |
| Source repositories of the controlled tasks (humanize, tinydb, inflection, more-itertools) | Base snapshots, upstream test files (overlays) and candidate patches | MIT (each repository's licence; notices in `THIRD_PARTY_LICENSES/`) |
| Ideas: oracle/no-op checks, cheat trials and hacker/fixer loops (Terminal-Bench task review); FAIL_TO_PASS/PASS_TO_PASS selection (SWE-bench family); separate verifier and artifact transfer (Harbor) | Design of audit:v1 and baseline B1 | cited in the research brief |

Wheel rows: licence as declared in each wheel's METADATA (`License-Expression`, else
the `License` field and licence classifiers), read on 2026-11-18 from the wheelhouses
`~/.cache/tracecontract/images/wheelhouse-<key>` of the three grading images: default
(`DEFAULT_TEST_REQUIREMENTS` in `docker_runner.py`, key `137c25ab71f8dfe8`), CS-01
(`0b1591bd588d585e`) and CS-02 to CS-04 (`801a26fad4c5e101`).

## AI-assisted work (substantial)

Produced with Claude (via Claude Code), reviewed only by the model so far:

* all package code, tests, scripts, CLI, report and Harbor exporter;
* the research notes and research brief (multi-agent literature review), the
  decision log, protocol v0.1, annotation guide, data card and the manuscript draft;
* the controlled-session scenarios (scripted user turns, including the corrections,
  and the intended requirements that define the labels) and their reference
  operationalisations, written by the same model as the session agent;
* the controlled sessions themselves (the coding agent is a Claude model), the
  recovered contracts, all generated verifiers, development attacks, valid
  alternatives, near misses, reference checks, and every proposed label;
* the independent construction checks, both requirement mappers, and the
  adversarial verification of the research brief (skeptics, citation and fact
  checks) together with the resulting revisions;
* the diagnosis and fixes of the five harness defects (D29–D31, D36, D40, D44), and
  of the result-formatting behaviour disclosed in D46, for which harness 0.3.4 was too
  narrow a fix and 0.3.5 is the one new runs use (D51, D52);
* the Harbor exporter's planted-reward defect and its fixes (`tc-harbor-export/0.2.0`
  and `0.3.0`, D51, D52), the reconstruction check that replaced the vacuous leakage
  check found in D47 (version 2: D52), and the enforced acceptance gate (D51, D52);
* protocol amendments v0.2 to v0.8, transcript sanitiser v2 (D38), the post-hoc
  analyses (D37), the exploratory re-analysis and the draft precision plan (D49), the
  CS-02 reference-check review loop, the CS-01 mapping correction (D42), the blinded
  review packet tooling (`tracecontract review-packet` and `merge-reviews`; D43, D44,
  D46), the strict re-audit of the generator transcripts (`scripts/strict_reaudit.py`,
  D44, D46) and the pilot's results text;
* the natural-data screening: the Trace Commons screen with transcript replay and
  triage, the AIDev funnel, the stage-S9 judgments and paraphrases, the
  pseudonymiser and the privacy scan of the sampled logins (D47, D48, D50, D52);
* the fresh-agent tooling (workspaces with the recorded path substitution, the
  fresh-attempt audit and `add-stratum-candidate`), the schema identifiers of protocol
  v0.8 and the reporting rules of new runs (D52);
* the six-lens internal review with its skeptic agents, the dispositions review, the
  final claims audit, the verification of the resulting fixes and the final
  verification (D36–D46), the re-audit against the specification (D47) and the
  verification of round 4 (D51), all run by model agents, and the fixes that followed
  them (through D52).

## Human decisions and reviews still required

1. **Contract review and candidate labels** for every task, by two reviewers per task
   working from the blinded review packet, and adjudication of their disagreements
   (`docs/annotation_guide.md`; protocol v0.6 §14). Until their labels are merged,
   reviewers open no task files, results or documents except the annotation guide;
   this document is one they must not open. Someone who has already read these files
   is not blind to the proposals and outcomes they state. Reviews alone cannot open
   the acceptance gate: it also needs a recorded provenance review and the owner
   decisions on the condition contracts and on where reviews are written (`STATUS.md`,
   Blocked).
2. **Data access**: accept the SWE-chat terms and supply a working read token. Two
   ungated, openly licensed sources need neither and were taken up for screening
   (D47): all 30 Trace Commons sessions were screened and rejected; in AIDev v5
   pull-request review threads, stage S9 is done (31 of 150 sampled comments qualify,
   as model proposals; D50) and stage S10 is under way. No natural task has been
   built. Decide whether pull-request review comments count as user corrections for
   the claim (D47).
3. **Scope of the claim.** The adversarial review (D34) narrowed it to a
   conjunction. SessionFarmer is the closest work; its Table 3 already compares
   suites with and without refinement on a held-out pool, with LLM labels. Confirm
   or revise the narrowed wording, and record the decision as a new decision-log
   entry (the log is append-only, so D25 is not edited).
4. **Repository licence** and the licence of released task data.
5. **Authorship, AI-use disclosure, and whether/when to submit anything.**
6. **Spending**: whether to approve any paid model or compute budget (default zero),
   e.g. for a second model family. Fresh-agent difficulty checks no longer need it:
   protocol v0.7 §15.4 plans them with subagents of the build session (none has run
   yet).

## Hard technical questions (be ready to answer these yourself)

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
10. Which parts of this project are new relative to SessionFarmer, SWE-Together,
    traj2envs and PersonaCodeBench? Which conclusions survive if the
    correction-aware improvement is zero?
11. Every container used to run candidate code as UID 1001. Why did that make
    grading outcomes depend on unrelated concurrent load? How does a per-container
    UID fix it? Which kernel limits are per user and which are per cgroup?
12. The pre-specified label rule marks hard near misses *ambiguous* and excludes
    them. In which direction does that bias false acceptance, and why for every
    condition? What does the exploratory construction-label analysis show, and why
    is it not primary?
13. In two of four sessions the pre-correction state is labeled valid. What does
    that say about using the state before a scripted correction as a negative? How
    would you sample natural sessions to estimate how often it happens?

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
6. Export a task to Harbor (`src/tracecontract/harbor_export.py`) with at least one
   named candidate (`export_task(..., candidates=[...])`; by default only the
   reference solution is packaged), run the oracle with two different `CANDIDATE`
   values, and check that Harbor's reward matches `tracecontract grade`. Then read
   how the exporter (since 0.2.0; now 0.3.0) keeps candidate code from writing its own
   reward file, and the two probes that show it (`scripts/harbor_validate.sh`).
