# Status

Last updated: 2026-11-18 (UTC). Milestone: **M2 complete** (automated pilot on four
controlled task families). **M3** (human labels, natural data) is blocked on the
repository owner. Nothing here is peer reviewed, and no human labels exist.

## Completed

* **Package `src/tracecontract/`:**
  * ingestion: schemas, Claude Code transcript ingestion and sanitisation;
  * contracts: recovery, validation and the acceptance gate;
  * snapshots with a leakage check, and the patch policy;
  * grading: a process-separated sandbox grader with trusted aggregation (harness
    `tc-harness/0.3.0`);
  * verifiers: specs (hashing, linting, freezing) and audit:v1;
  * evaluation: the evaluation matrix, and metrics (FA/FR, task-family cluster
    bootstrap, paired differences);
  * reporting: analysis (label policies, contradiction-aware contract coverage,
    mapper agreement, review queue, exploratory sensitivity), static HTML report,
    Harbor export and the CLI.
* **Tasks.** Four controlled sessions (protocol CS-v1) compiled into `tasks/CS-01` …
  `tasks/CS-04`. Per task:
  * contracts: initial-only and full-session contracts, plus a reference contract
    built from the pre-registered intended requirements;
  * verifiers C1–C4, B1 and B2, plus frozen independent reference checks;
  * held-out pool: pre-correction state, 2 valid alternatives and 5 near misses,
    generated after freezing, with generator transcripts audited (0 forbidden
    reads);
  * labels: D19 label proposals and independent construction checks;
  * review queue: `labels/review_queue.json`, with no verifier outcomes;
  * two model requirement mappings.
* **Protocol** v0.1 → v0.2 → v0.3 (`experiments/protocol.md`). Each version was
  hashed and logged before the runs it governs (D15, D32).
* **Final pilot run** `results/runs/pilot-v0.3`:
  * 240 pairs, harness 0.3.0, one code revision, no infrastructure outcomes;
  * analysis, report (`report.html`) and comparisons with the superseded runs
    `pilot-v0.2` (107/108 pairs agree) and `pilot-v0.2-h2`.
* **Research brief** adversarially verified, using close reading, a fresh search,
  citation verification and a fact check (`docs/research/review_*.md`). Related work
  rewritten from the verified findings; bibliography verified on 2026-11-18. The
  claim is narrowed to a conjunction (D34), pending owner confirmation.
* **Manuscript draft** (`paper/`):
  * all sections drafted;
  * every table generated from records (`paper/make_tables.py`);
  * an evidence ledger;
  * compiles to 20 pages.
* **Other documents:** annotation guide v0.2, data card, decision log D1–D34,
  submission-readiness notes (arXiv pages re-checked 2026-11-18), and the
  ownership/defense notes.

## Tested

* **58 tests pass:** 45 offline and 13 Docker.
* **Offline tests:**
  * schemas, ingestion and evidence alignment;
  * supersession, contract validation and the acceptance gate;
  * patch policy, leakage check, and verifier lint/freeze;
  * trusted aggregation: missing, stale or crashed results never pass;
  * metrics, label policies, coverage and κ;
  * audit hold-out guard.
* **Docker probes of the grading boundary:**
  * results are not writable and hidden tests are not readable;
  * the grader cannot be signalled, and there is no network;
  * the UID is unprivileged and unique to the container;
  * timeouts and fork bombs are contained, and daemons are reaped;
  * forged or rewritten results are detected, protected test edits are discarded,
    and path traversal is rejected;
  * per-UID limits are not shared across containers;
  * thread capacity holds after allocation churn.
* **Characterisation probe:** the in-process repository-test baseline (B1) can be
  forged by an adversarial candidate. This is a documented limitation.
* **Harbor:** export validated with oracle and no-op trials on a fixture task.

## Main pilot findings (automated labels; descriptive only)

* **Initial-only verifiers.** C1 accepts 6/17 invalid held-out candidates, all of
  them correction-violating, and rejects 2/10 valid ones.
* **Correction-aware verifiers.** C3 and C4 accept 0/17 and reject 0/10.
* **Baselines.** B2 accepts 1/17. B1 accepts 5/17 and rejects 4/10.
* **Audit.** It changed one outcome out of 64.
* **Selection effect.** The 5 ambiguous near misses are the hard cases. Labeled by
  construction intent (exploratory), they bring C3 and C4 to 3/22 false acceptance.
* **Anchor states.** 2 of 4 pre-correction states are labeled valid. In one task the
  initial-only contract proposer inferred the whole correction.

## In progress

* Adversarial internal review of the repository and the manuscript (workflow with
  six lenses). Findings and dispositions will go into `docs/internal_review.md`.

## Blocked (needs the repository owner)

* **Human annotation.** Contracts and the 32 held-out candidates need review by a
  qualified human (`docs/annotation_guide.md`; queue in
  `tasks/*/labels/review_queue.json`). The paper's central claim needs them.
* **Natural data (SWE-chat).** The dataset's Hugging Face terms must be accepted by
  the owner, and the saved token fails authentication (`/api/whoami-v2` → 401).
* **Harbor `no-network` on this host.** Harbor's egress control needs nftables
  support this host lacks. Exported tasks declare `no-network`, and a
  `local-validation` variant is used only for oracle/no-op checks.
* **Owner decisions:** the claim wording (D34), the repository licence, any
  spending, authorship and AI-use disclosure, and whether and when to submit.

## Not run

* Any natural-data task, any second-annotator agreement, any fresh-agent difficulty
  check, any second model family, and any downstream training experiment (no GPU
  and no approved spending).
