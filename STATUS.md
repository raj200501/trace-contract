# Status

Last updated: 2026-11-13 (UTC). Milestone in progress: **M1 → M2** (pilot on
controlled sessions). Nothing here is peer reviewed; no human labels exist yet.

## Completed

* Environment: Docker sandbox (offline images from pinned wheelhouses), LaTeX,
  Harbor 0.25.0 installed in a scratch venv for integration probes.
* Package `src/tracecontract/`: schemas, Claude Code transcript ingestion and
  sanitisation, contract recovery/validation/acceptance gate, snapshots with
  leakage check, patch policy, process-separated sandbox grader with trusted
  aggregation, verifier specs (hashing, linting, freezing), audit:v1, evaluation
  matrix, metrics (FA/FR with task-family cluster bootstrap), analysis tables,
  static HTML report, Harbor export, CLI.
* Controlled-session protocol CS-v1 with pre-registered scenarios CS-01…CS-04
  (hashes in `docs/decision_log.md`).
* CS-01 compiled into `tasks/CS-01` (session, snapshot, reference contract pending
  human review, natural candidates, B1 repository-tests verifier).
* Protocol v0.1 (`experiments/protocol.md`), annotation guide, data card, decision log.

## Tested

* Unit tests: schemas, ingestion, evidence alignment, supersession, contract
  validation and acceptance gate, patch policy, leakage check, verifier lint/freeze,
  trusted aggregation (missing/stale/crashed results never pass), metrics, audit
  hold-out guard.
* Docker integration tests of the grading boundary (results file not writable,
  hidden tests not readable, grader not signalable, no network, unprivileged UID,
  timeouts, fork bombs, daemon reaping, forged/rewritten results detected,
  protected test edits discarded, path traversal rejected).

## In progress

* Research brief (multi-agent literature/data review) - notes in `docs/research/notes/`.
* CS-01 verifier generation (contracts, C1-C4, B2, dev attacks/alternatives, audit).
* Controlled sessions CS-02…CS-04.

## Blocked

* **Natural data (SWE-chat):** the dataset's Hugging Face terms must be accepted by
  the repository owner; the saved token currently fails authentication
  (`/api/whoami-v2` → 401), so it may be a placeholder or invalid. Needs a valid
  read token after accepting the terms.
* **Human annotation:** reference contracts and candidate labels need review by a
  qualified human (`docs/annotation_guide.md`). Until then all results are an
  automated pilot.
* **Harbor `no-network` on this host:** Harbor's egress control needs nftables
  support that this host lacks; exported tasks declare `no-network`, and a
  `local-validation` variant is used only for oracle/no-op checks.
* **Repository licence:** not chosen yet (owner decision).

## Not run

* Any natural-data task, any second-annotator agreement, any fresh-agent difficulty
  check, any downstream training experiment (no GPU and no approved spending; see
  the brief's training section).
