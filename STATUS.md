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
    `tc-harness/0.3.2`);
  * verifiers: specs (hashing, linting, freezing) and audit:v1;
  * evaluation: the evaluation matrix, and metrics (FA/FR, task-family cluster
    bootstrap, paired differences);
  * reporting: analysis (label policies, contradiction-aware contract coverage,
    mapper agreement, review queue, exploratory sensitivity), static HTML report,
    Harbor export and the CLI;
  * checks: same-code duplicate detection (`scripts/find_duplicates.py`) and a scan
    of every file git would publish (`scripts/scan_tracked_files.py`).
* **Tasks.** Four controlled sessions (protocol CS-v1) compiled into `tasks/CS-01` …
  `tasks/CS-04`. Per task:
  * contracts: initial-only and full-session contracts, plus a reference contract
    built from the intended requirements, which were hashed and logged locally
    before each session ran. The study's AI agent, the same model as the session
    agent, wrote the scenarios and their reference operationalisation;
  * verifiers C1–C4, B1 and B2, plus frozen independent reference checks;
  * held-out pool: the pre-correction state, captured during the session, plus 2
    valid alternatives and 5 near misses generated after the task's verifiers were
    frozen (CS-04's B1 was re-selected afterwards, D31). The generator audits found
    0 forbidden reads but inspect tool inputs only. Near-miss generators ran B1's
    tests, and three held-out candidates duplicate a development attack (D37, D40,
    D41);
  * labels: D19 label proposals and independent construction checks;
  * review queue: `labels/review_queue.json`, with no verifier outcomes;
  * two model requirement mappings.
* **Protocol** v0.1 → v0.2 → v0.3 → v0.4 → v0.5 (`experiments/protocol.md`). Each
  version was hashed and logged locally before the runs it governs (D15, D22, D32,
  D39, D40). This is not a formal preregistration.
* **Final pilot run** `results/runs/pilot-v0.3.2`:
  * 240 pairs, harness 0.3.2, one code revision, no infrastructure outcomes;
  * labels re-proposed under 0.3.2 first, identical to the earlier proposals (D40);
  * agrees with `pilot-v0.3.1` (harness 0.3.1) and `pilot-v0.3` (0.3.0) on all 240
    pairs, in reward and in exact outcome;
  * analysis, report (`report.html`), and comparisons with the superseded runs
    `pilot-v0.3.1` (harness 0.3.1), `pilot-v0.3` (0.3.0), `pilot-v0.2` and
    `pilot-v0.2-h2`.
* **Research brief** adversarially verified by model agents (close reading, a fresh
  search, citation verification and a fact check; `docs/research/review_*.md`); not
  yet reviewed by a human. Related work rewritten from the verified findings;
  bibliography verified on 2026-11-18. The claim is narrowed to a conjunction (D34),
  pending owner confirmation.
* **Manuscript draft** (`paper/`):
  * all sections drafted;
  * every table generated from records (`paper/make_tables.py`);
  * an evidence ledger listing every table number with its source file;
  * compiles to PAGES_PLACEHOLDER pages.
* **Reviews by model agents** (Claude, the same model family; not human review):
  * an internal review with six lenses, whose skeptic agents checked findings until
    that stage was stopped for the final run;
  * a review of how each of its findings was resolved;
  * a final audit of every public claim and number (D40).

  Findings, verdicts and dispositions are in `docs/internal_review.md`.
* **Other documents:** annotation guide v0.2, data card, decision log D1–D42,
  submission-readiness notes (arXiv pages re-checked 2026-11-18), the
  ownership/defense notes, workflow and agent prompts (`experiments/prompts/`), and
  third-party licence notices (`THIRD_PARTY_LICENSES/`).

## Tested

* **TESTS_PLACEHOLDER**
* **Offline tests:**
  * schemas, ingestion and evidence alignment;
  * supersession, contract validation and the acceptance gate;
  * patch policy, leakage check, and verifier lint/freeze (re-freezing refused, the
    check-list hash required);
  * trusted aggregation: missing, stale or crashed results never pass;
  * metrics, label policies, coverage and κ;
  * same-code duplicate detection and the Harbor export layout;
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
  * a candidate `encodings` package cannot forge results at interpreter start;
  * startup hooks and packages written at runtime never load in later calls.
* **Characterisation probe:** the in-process repository-test baseline (B1) can be
  forged by an adversarial candidate. This is a documented limitation (D42).
* **Harbor:** HARBOR_PLACEHOLDER

## Main pilot findings (automated labels; descriptive only)

* **Initial-only verifiers.** C1 accepts 6/17 invalid held-out candidates and
  rejects 2/10 valid ones. Every candidate it accepts is correction-violating, as 16
  of the 17 invalid candidates are.
* **Correction-aware verifiers.** C3 and C4 accept 0/17 and reject 0/10, under the
  rule's labels. They accept all three valid-labeled candidates that the independent
  check disputes.
* **Baselines.**
  * B2 accepts 1/17.
  * B1 accepts 5/17 and rejects 4/10. All four rejections come from tests the
    session agent added. On upstream tests only (exploratory), B1 accepts 13/17 and
    rejects 0/10; both numbers largely follow from the label rule. B1's near-miss
    outcomes are not blind to construction (D37).
* **Audit.** Four of the eight audited verifiers are identical to the plain ones. On
  the other four it changed one outcome out of 32.
* **Selection effect.** The 5 ambiguous near misses are the hard cases. Two
  exploratory relabelings raise C3/C4 false acceptance:
  * 3/22 when labeled by construction intent;
  * 6/25 when labeled by the independent construction checks.
* **Duplicates.** Without the three held-out candidates that duplicate a
  development attack (exploratory), C1 accepts 4/14 and C3/C4 0/14.
* **Anchor states.** 2 of 4 pre-correction states are labeled valid. In one task the
  initial-only contract proposer inferred the whole correction.
* **Intervals.** Cluster-bootstrap intervals are degenerate where all four families
  have the same rate or difference; they are marked, and exact binomial intervals
  are reported next to them.

## Blocked (needs the repository owner)

* **Human annotation.** Contracts and the 32 held-out candidates need review by a
  qualified human (`docs/annotation_guide.md`; queue in
  `tasks/*/labels/review_queue.json`). The paper's central claim needs them.
* **Natural data (SWE-chat).** The dataset's Hugging Face terms must be accepted by
  the owner, and the saved token fails authentication (`/api/whoami-v2` → 401).
* **Harbor `no-network` on this host.** Harbor rejected `no-network` on this host
  (the rejection was observed; its cause was not probed). Exported tasks declare
  `no-network`, and a `local-validation` variant is used only for oracle/no-op
  checks.
* **Owner decisions:**
  * the claim wording (D34);
  * the repository licence;
  * any spending;
  * authorship, the AI-use disclosure and any competing-interests statement;
  * whether and when to submit;
  * whether to delete the third-party session data and other downloads kept outside
    the repository (`data/manifests/third_party_downloads.json`);
  * whether to rewrite the branch's git history. Earlier commits, already pushed,
    still contain material that the reviews removed from the working tree
    (`docs/internal_review.md`, P1, P7, P9):
    * the earlier research notes;
    * the exported research prompt in `8c13e0c`;
    * redaction rules in `c830977`;
    * original-script hashes in the prompt exports of `c830977` and `c37b941`;
    * session ids and session-local scratchpad paths in
      `tasks/CS-0{1,3,4}/labels/generator_audit.json` (commits `0339400` to
      `f6c8e9f`).

    A rewrite needs a force-push and cannot recall copies already fetched. No
    history has been rewritten.

## Not run

* Any natural-data task, any second-annotator agreement, any fresh-agent difficulty
  check, any second model family, and any downstream training experiment (no GPU
  and no approved spending).
