# Status

Last updated: 2026-11-13 (UTC). Milestone in progress: **M2** (automated pilot on
four controlled task families). Nothing here is peer reviewed; no human labels exist.

## Completed

* Package `src/tracecontract/`: schemas, Claude Code transcript ingestion and
  sanitisation, contract recovery/validation/acceptance gate, snapshots with
  leakage check, patch policy, process-separated sandbox grader with trusted
  aggregation (harness `tc-harness/0.2.0`), verifier specs (hashing, linting,
  freezing), audit:v1, evaluation matrix, metrics (FA/FR with task-family cluster
  bootstrap), analysis tables, static HTML report, Harbor export, CLI.
* Controlled-session protocol CS-v1; four pre-registered scenarios run with a real
  coding agent and compiled into `tasks/CS-01` … `tasks/CS-04` (hashes and
  deviations in `docs/decision_log.md`).
* Per task: initial-only and full-session contracts (`contract:v1`), verifiers C1–C4,
  B1 (repository tests at the reference state), B2 (full-session LLM tests);
  dev attacks/alternatives; audit:v1 on C2/C4 run on the host and recorded; all
  verifiers frozen before any held-out candidate was generated.
* Held-out candidates generated after freezing by separate agents in isolated
  workspaces (2 valid alternatives, 5 near misses per task, plus the observed
  pre-correction state); every generator transcript audited for forbidden reads
  (`tasks/*/labels/generator_audit.json`).
* Independent reference checks per task (validated only on reference and no-op) and
  automated label proposals by the pre-specified rule D19.
* Protocol v0.2 (`experiments/protocol.md`, hashed before the first evaluation run),
  annotation guide, data card, decision log (D1–D29).

## Tested

* 53 tests pass (42 offline, 11 Docker): schemas, ingestion, evidence alignment,
  supersession, contract validation and acceptance gate, patch policy, leakage
  check, verifier lint/freeze, trusted aggregation (missing/stale/crashed results
  never pass), metrics, audit hold-out guard; Docker probes of the grading
  boundary (results not writable, hidden tests not readable, grader not
  signalable, no network, per-container unprivileged UID, timeouts, fork bombs,
  daemon reaping, forged/rewritten results detected, protected test edits
  discarded, path traversal rejected, per-UID limits not shared across containers).
* Harbor export validated with oracle/no-op trials on a fixture task.

## Paused here (2026-11-13, at the owner's request)

All agents and jobs were stopped; nothing is running. Exact state:

* **Harness:** 0.2.0 fixes the shared-UID limit (D29). A second nondeterministic
  stall was found under 0.2.0 (D30: address-space cap + glibc arenas). The fix is
  planned but **not implemented**; no further evaluation should run before it.
* **Runs:** `pilot-v0.2` (harness 0.1.0; CS-03 and CS-04 complete, 108 pairs) and
  `pilot-v0.2-h2` (harness 0.2.0; stopped after 4 pairs) are both superseded. No
  run is final, so no results are reported yet (README keeps its placeholder).
* **Tasks:**
  * CS-03, CS-04: all verifiers frozen; held-out candidates, generator audits and
    D19 label proposals done. Labels must be re-proposed under the fixed harness.
  * CS-01: verifiers and reference checks frozen; two valid alternatives done;
    **near misses not yet generated** (two attempts stopped).
  * CS-02: all verifiers frozen, reference material unsealed; **held-out
    candidates, reference checks and contract mapping not yet generated** (agents
    stopped while reading, nothing registered).
* **Research brief:** the citation/fact-check workflow was stopped before it
  finished; the brief and related-work section are unverified drafts.

### Next steps, in order

1. Implement D30 (`MALLOC_ARENA_MAX=2` in `tc_sandbox._sandbox_env`, thread-churn
   probe in `tests/test_sandbox_isolation.py`, harness 0.3.0); run all tests.
2. Generate CS-01 near misses and CS-02 held-out candidates, reference checks and
   mapping (prompt templates: the generator transcripts' first messages); audit
   their transcripts with `scripts/audit_eval_generators.py`; freeze reference checks.
3. Propose labels for all four tasks (`scripts/propose_labels.py`).
4. One evaluation run of all tasks under 0.3.0; `analyze`, `report`,
   `scripts/compare_runs.py` against the superseded runs.
5. Paper tables (`paper/make_tables.py`), results text, README, adversarial review.

## Blocked (needs the repository owner)

* **Natural data (SWE-chat):** the dataset's Hugging Face terms must be accepted by
  the owner, and the saved token fails authentication (`/api/whoami-v2` → 401).
* **Human annotation:** reference contracts and candidate labels need review by a
  qualified human (`docs/annotation_guide.md`). Until then all results are an
  automated pilot. Candidates the D19 rule marks ambiguous are queued for review.
* **Harbor `no-network` on this host:** Harbor's egress control needs nftables
  support that this host lacks; exported tasks declare `no-network`, and a
  `local-validation` variant is used only for oracle/no-op checks.
* **Repository licence and any spending:** owner decisions.

## Not run

* Any natural-data task, any second-annotator agreement, any fresh-agent difficulty
  check, any downstream training experiment (no GPU and no approved spending).
