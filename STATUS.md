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
    `tc-harness/0.3.1`);
  * verifiers: specs (hashing, linting, freezing) and audit:v1;
  * evaluation: the evaluation matrix, and metrics (FA/FR, task-family cluster
    bootstrap, paired differences);
  * reporting: analysis (label policies, contradiction-aware contract coverage,
    mapper agreement, review queue, exploratory sensitivity), static HTML report,
    Harbor export and the CLI.
* **Tasks.** Four controlled sessions (protocol CS-v1) compiled into `tasks/CS-01` …
  `tasks/CS-04`. Per task:
  * contracts: initial-only and full-session contracts, plus a reference contract
    built from the intended requirements, which were hashed and logged locally
    before each session ran;
  * verifiers C1–C4, B1 and B2, plus frozen independent reference checks;
  * held-out pool: pre-correction state, 2 valid alternatives and 5 near misses,
    generated after freezing, with generator transcripts audited (0 forbidden
    reads);
  * labels: D19 label proposals and independent construction checks;
  * review queue: `labels/review_queue.json`, with no verifier outcomes;
  * two model requirement mappings.
* **Protocol** v0.1 → v0.2 → v0.3 → v0.4 (`experiments/protocol.md`). Each version
  was hashed and logged locally before the runs it governs (D15, D32, D39). This is
  not a formal preregistration.
* **Final pilot run** `results/runs/pilot-v0.3.1`:
  * 240 pairs, harness 0.3.1, one code revision, no infrastructure outcomes;
  * labels re-proposed under 0.3.1 first, identical to the earlier proposals (D39);
  * agrees with `pilot-v0.3` (harness 0.3.0) on all 240 pairs, in reward and in
    exact outcome;
  * analysis, report (`report.html`), and comparisons with the superseded runs
    `pilot-v0.3` (harness 0.3.0), `pilot-v0.2` and `pilot-v0.2-h2`.
* **Research brief** adversarially verified, using close reading, a fresh search,
  citation verification and a fact check (`docs/research/review_*.md`). Related work
  rewritten from the verified findings; bibliography verified on 2026-11-18. The
  claim is narrowed to a conjunction (D34), pending owner confirmation.
* **Manuscript draft** (`paper/`):
  * all sections drafted;
  * every table generated from records (`paper/make_tables.py`);
  * an evidence ledger;
  * compiles to 22 pages.
* **Adversarial internal review** (six lenses; every finding checked by independent
  skeptics until the skeptic stage was stopped for the final run). Findings, verdicts
  and dispositions are in `docs/internal_review.md`.
* **Other documents:** annotation guide v0.2, data card, decision log D1–D39,
  submission-readiness notes (arXiv pages re-checked 2026-11-18), the
  ownership/defense notes, workflow and agent prompts (`experiments/prompts/`), and
  third-party licence notices (`THIRD_PARTY_LICENSES/`).

## Tested

* **60 tests pass:** 45 offline and 15 Docker.
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
  * thread capacity holds after allocation churn;
  * a candidate module that shadows the standard library cannot forge results;
  * startup hooks written at runtime never run in later calls.
* **Characterisation probe:** the in-process repository-test baseline (B1) can be
  forged by an adversarial candidate. This is a documented limitation.
* **Harbor:** export validated with oracle and no-op trials on a fixture task under
  harness 0.3.1 (Harbor 0.25.0; D35, D39).

## Main pilot findings (automated labels; descriptive only)

* **Initial-only verifiers.** C1 accepts 6/17 invalid held-out candidates and
  rejects 2/10 valid ones. Every candidate it accepts is correction-violating, as 16
  of the 17 invalid candidates are.
* **Correction-aware verifiers.** C3 and C4 accept 0/17 and reject 0/10.
* **Baselines.**
  * B2 accepts 1/17.
  * B1 accepts 5/17 and rejects 4/10. All four rejections come from tests the
    session agent added. On upstream tests only (exploratory), B1 accepts 13/17 and
    rejects 0/10.
* **Audit.** Four of the eight audited verifiers are identical to the plain ones. On
  the other four it changed one outcome out of 32.
* **Selection effect.** The 5 ambiguous near misses are the hard cases. Two
  exploratory relabelings raise C3/C4 false acceptance:
  * 3/22 when labeled by construction intent;
  * 6/25 when labeled by the independent construction checks.
* **Anchor states.** 2 of 4 pre-correction states are labeled valid. In one task the
  initial-only contract proposer inferred the whole correction.
* **Intervals.** Cluster-bootstrap intervals are degenerate where all four families
  have the same rate. Exact binomial intervals are reported next to them.

## Blocked (needs the repository owner)

* **Human annotation.** Contracts and the 32 held-out candidates need review by a
  qualified human (`docs/annotation_guide.md`; queue in
  `tasks/*/labels/review_queue.json`). The paper's central claim needs them.
* **Natural data (SWE-chat).** The dataset's Hugging Face terms must be accepted by
  the owner, and the saved token fails authentication (`/api/whoami-v2` → 401).
* **Harbor `no-network` on this host.** Harbor's egress control needs nftables
  support this host lacks. Exported tasks declare `no-network`, and a
  `local-validation` variant is used only for oracle/no-op checks.
* **Owner decisions:**
  * the claim wording (D34);
  * the repository licence;
  * any spending;
  * authorship and AI-use disclosure;
  * whether and when to submit;
  * whether to rewrite the branch's git history. Earlier commits still contain
    material that the internal review removed from the working tree
    (`docs/internal_review.md`, P1 and P7): the earlier research notes, the
    exported research prompt in `8c13e0c`, and redaction rules in `c830977`. No
    history has been rewritten. The final run's manifest records commit `c830977`.

## Not run

* Any natural-data task, any second-annotator agreement, any fresh-agent difficulty
  check, any second model family, and any downstream training experiment (no GPU
  and no approved spending).
