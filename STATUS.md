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
    `tc-harness/0.3.3`). A later verification by model agents found a further path
    for forged results in the error handling of 0.3.2, which harness 0.3.3 closes (D44).
    Within one call, code that the snippet runs still controls what that call
    reports, so every test of the process-separated verifiers asserts on a returned
    value, not only on success (the in-call limit; D3, D36, D40);
  * verifiers: specs (hashing, linting, freezing) and audit:v1;
  * evaluation: the evaluation matrix, and metrics (FA/FR, task-family cluster
    bootstrap, paired differences);
  * reporting: analysis (label policies, contradiction-aware contract coverage,
    mapper agreement, review queue, exploratory sensitivity), static HTML report,
    Harbor export and the CLI;
  * checks: same-code duplicate detection (`scripts/find_duplicates.py`), a stricter
    re-audit of the generator transcripts (`scripts/strict_reaudit.py`, D44), and a
    scan of the working tree and of every file version in the commits a push would
    send (`scripts/scan_tracked_files.py`). The scan is a manual step before each
    push, run with a private-marker file kept outside the repository; it is not a
    git hook (D44).
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
    0 forbidden reads but inspect tool inputs only. The generators, the
    reference-check writers and their reviewers shared the build session's scratch
    directory, which also held other agents' files and some material derived from
    candidates; the first audit treated only its sealed subfolders as forbidden. A
    stricter re-audit, which treats the whole directory as forbidden, found no read
    of candidate, verifier or sealed material. Some listings showed file names
    (`git status` among them, which named held-out CS-02 candidate files), and one
    reviewer read all of another reviewer's test runner there, which holds no
    candidate or other verifier material (D44, D46). Near-miss generators ran B1's tests, and three held-out
    candidates duplicate a development attack (D37, D40, D41);
  * labels: D19 label proposals and independent construction checks; a blinded
    review packet for human labels (`tracecontract review-packet`, D43, D44), which
    hides the origin field but not what the content reveals about origin;
  * review queue: `labels/review_queue.json`, with no verifier outcomes, which
    reviewers open only after their labels are merged;
  * two model requirement mappings.
* **Protocol** v0.1 → v0.2 → v0.3 → v0.4 → v0.5 → v0.6 (`experiments/protocol.md`).
  Each version was hashed and logged locally before the runs it governs (D15, D22,
  D32, D39, D40, D44). This is not a formal preregistration.
* **Final pilot run** `results/runs/pilot-v0.3.3`:
  * 240 pairs, harness 0.3.3, one code revision, no infrastructure outcomes;
  * labels re-proposed under 0.3.3 first, identical to the earlier proposals (D45);
  * agrees with `pilot-v0.3.2` (harness 0.3.2), `pilot-v0.3.1` (0.3.1) and
    `pilot-v0.3` (0.3.0) on all 240 pairs, in reward and in exact outcome;
  * analysis, report (`report.html`), and comparisons with the superseded runs
    `pilot-v0.3.2`, `pilot-v0.3.1`, `pilot-v0.3`, `pilot-v0.2` and `pilot-v0.2-h2`.
* **Research brief** adversarially verified by model agents (close reading, a fresh
  search, citation verification and a fact check; `docs/research/review_*.md`); not
  yet reviewed by a human. Related work rewritten from the verified findings;
  bibliography verified on 2026-11-18. The claim is narrowed to a conjunction (D34),
  pending owner confirmation.
* **Manuscript draft** (`paper/`):
  * all sections drafted;
  * every table generated from records (`paper/make_tables.py`);
  * an evidence ledger listing every table number with its source file;
  * compiles to 27 pages.
* **Reviews by model agents** (Claude, the same model family; not human review):
  * an internal review with six lenses, whose skeptic agents checked findings until
    that stage was stopped for the final run;
  * a review of how each of its findings was resolved;
  * a final audit of every public claim and number (D40);
  * a verification of the fixes that followed them (D44), after which a second
    workflow corrected the text in six batches, each checked by a second agent (D45);
  * a final read-only verification of all of round 3, whose findings were fixed or
    disclosed (D46).

  Findings, verdicts and dispositions are in `docs/internal_review.md`.
* **Other documents:** annotation guide v0.4 (blinded review packet, D43, D44), data
  card, decision log D1–D46,
  submission-readiness notes (arXiv pages re-checked 2026-11-18), the
  ownership/defense notes, workflow and agent prompts (`experiments/prompts/`), and
  third-party licence notices (`THIRD_PARTY_LICENSES/`).

## Tested

* **80 tests pass** (2026-11-18, after the final run): 63 offline and 17 Docker.
* **Offline tests:**
  * schemas, ingestion and evidence alignment;
  * supersession, contract validation and the acceptance gate;
  * patch policy, leakage check, and verifier lint/freeze (re-freezing refused, the
    check-list hash required);
  * trusted aggregation: missing, stale or crashed results never pass;
  * metrics, label policies, coverage and κ;
  * same-code duplicate detection and the Harbor export layout;
  * audit hold-out guard;
  * the blinded review packet and its merge (type checks, all-or-nothing writes,
    disagreement on violated requirements), and the strict re-audit (26 shell forms,
    attribution of scratch-directory reads).
* **Docker probes of the grading boundary:**
  * results are not writable and hidden tests are not readable;
  * the grader cannot be signalled, and there is no network;
  * the UID is unprivileged and unique to the container;
  * timeouts and fork bombs are contained, and daemons are reaped;
  * forged or rewritten results are detected, protected test edits are discarded,
    and path traversal is rejected;
  * per-UID limits are not shared across containers;
  * thread capacity holds after allocation churn;
  * a candidate `json.py` that shadows the standard library cannot forge results;
  * a candidate `encodings` package cannot forge results at interpreter start;
  * startup hooks and packages written at runtime never load in later calls;
  * a candidate `ast` module cannot forge the result of a snippet that raises (D44).
* **Characterisation probe:** the in-process repository-test baseline (B1) can be
  forged by an adversarial candidate. This is a documented limitation (D42).
* **Harbor:** export validated with oracle and no-op trials on a fixture task under
  harness 0.3.3 (Harbor 0.25.0; D35, D39, D40, D45). The outputs are recorded in
  `results/harbor_validation/tc-harness-0.3.3/` (and, for 0.3.2,
  `tc-harness-0.3.2/`).

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

* **Human annotation.** Contracts and the 32 held-out candidates need review by two
  qualified human reviewers per task. A coordinator builds the blinded review packet
  (`tracecontract review-packet`) and keeps its key. The reviewers work from the
  packet only, following `docs/annotation_guide.md`, and `tracecontract
  merge-reviews` merges their labels once every task has two complete reviews. The
  queue (`tasks/*/labels/review_queue.json`) is opened only after the merge. The
  paper's central claim needs these labels.
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
    still contain material that has since been removed from the working tree
    (`docs/internal_review.md`, P1, P7, P9; D44 to D46):
    * the earlier research notes;
    * the exported research prompt in `8c13e0c`;
    * redaction rules in `scripts/export_prompts.py` that spell out the owner's
      context (commits `8c13e0c` to `74f6c73`): the first version quotes the start of
      an owner message, and one rule in `c830977` and `74f6c73` is built from part of
      the build session's id;
    * a note about the owner's messages in five exported held-out workflow scripts
      (`8c13e0c` to `feab025`);
    * hashes that are now withheld: original-script hashes in the prompt exports, the
      original-prompt hash of one agent in `experiments/prompts/agent_prompts.jsonl`
      (commits `8c13e0c` to `c37b941`), and the original hashes of the prompts and
      scripts from which a note about the owner's messages was removed (`8c13e0c` to
      `aa41b45`);
    * an earlier wording of one line of the ethics section (`3d3024a` to `787176e`);
    * the build session's id, in most files as part of its scratchpad path: in seven
      research notes (commits `2a81036` to `f6c8e9f`), in
      `scripts/compile_controlled.py` (`cbb8dcd` to `89ccce5`) and in
      `tasks/CS-0{1,3,4}/labels/generator_audit.json` (`0339400` to `f6c8e9f`).

    A rewrite needs a force-push and cannot recall copies already fetched. No
    history has been rewritten.
  * whether to keep the co-author and `Claude-Session` lines that end every commit
    message (the session's attribution rules add them).

## Not run

* Any natural-data task, any second-annotator agreement, any fresh-agent difficulty
  check, any second model family, and any downstream training experiment (no GPU
  and no approved spending).
