# Status

Last updated: 2026-11-22 (UTC), at the wrap-up of round 4 (decision log D47 to D66). Nothing here is peer reviewed, and
no human labels exist.

## Where the study stands

* **Lead result: fresh-agent attempts (`fresh-v1`, D61, D62).** 80 new agent attempts on the four controlled tasks,
  79 distinct graded patches, harness 0.3.5 with 3 repeats. Of the 40 attempts that saw only the first request, 27
  violate the correction. The initial-only verifiers (C1, C2) accept 24 of them; C3, C4, B2 and B1 accept none.
  * The audit removed no false acceptance and added 6 false rejections (C4, CS-03).
  * B2 matches C3 and C4 on false acceptance.
  * All 34 of B1's false rejections come from tests the session agent added.
  * Labels are model proposals: the independent labeler agrees with D19 on 77 of 79 units. The study has four
    families, so no two-sided p below 0.125 is possible, and the result is descriptive.
* **Construction pilot (`pilot-v0.3.3`).** A development study since protocol v0.7. Its re-grade under harness 0.3.5
  gives the same outcome on all 240 pairs (D54).
* **Natural PR-review arm (`natural-pr-v1`).**
  * Screening is done for both samples: 31 of 150 and 91 of 534 comments qualify at S9 (model-judged; D63, D66).
  * S10 is done for the first sample, with 6 of 22 families accepted. The extension's S10 was stopped and is to be
    redone.
  * The recipe is fixed (D64), and the six families' inputs and proposer prompts are logged (D65).
  * No natural agent has run, and every natural result is pending.
* **Manuscript (`paper/`).** Rebuilt findings-first around fresh-v1 (D66). It compiles, and every number in it is a
  generated macro with a ledger entry, or a decision-log count. Natural results are marked `UNFILLED`. Authors are a
  TODO for the human authors.

## Why the work stopped, and how to resume

* **Usage limit.** The build session's agents reached the account's weekly usage limit at about 18:50Z on 2026-11-21
  (it resets on 2026-11-25 at 07:00Z). The owner then asked for a wrap-up (D66).
* **To resume the natural arm,** after the reset, in this order:
  1. Done in round 5 (D69): the analysis of natural runs (WP-G) and the privacy and publication tools (WP-H1) are
     finished and merged.
  2. Done in round 5 (D69): the code's citations of the recipe name D64.
  3. Redo the extension's S10.
  4. Run D64's phases P1 to P7 for each accepted family, committing `data/manifests/natural_phase_ends.jsonl` after
     each phase (`scripts/record_phase_end.py`, D65).
  5. Propose the D19 labels, run the pre-flight, then the run `natural-pr-v1` and its analysis.
* **Owner decisions pending.**
  * Deviation (i) and the other builder decisions of D64.
  * How the scan treats organisation accounts, before its `--aidev-logins` mode loads both S9 samples (D66).
  * The human labels, and SWE-chat's access terms (below).

## Completed

* **Package `src/tracecontract/`:**
  * ingestion: schemas, Claude Code transcript ingestion and sanitisation;
  * contracts: recovery, validation and the acceptance gate, which `tracecontract
    accept-task` applies and `evaluate` enforces (a task that has not passed it is
    evaluated only with `--pilot`; none has passed, and none can yet: see Blocked).
    The gate takes each human reviewer's latest decision on a requirement: reviewers
    who disagree need an adjudicated review, and `edit` or `needs_discussion` blocks
    the requirement until a re-review accepts it. It also requires an `eligible`
    provenance record and a passed reconstruction record made from the current files
    (D51, D52; the rules await the owner's confirmation, DOCU-23);
  * snapshots and the patch policy. The leakage check recorded in each
    `snapshot.json` was vacuous as called: it compared the base with itself, so it
    could flag only a `.git` directory (D47). New builds record none. Each base is
    checked against its own session instead (`tracecontract reconstruction-check`,
    version 2 since D52; records in `tasks/*/reconstruction_check.json`). Version 2
    rolls the result up per changed file: a file without a passed first-edit or
    base-read item makes it incomplete, which is how a leak masked by a shell command
    the check cannot follow now shows. The command exits 0 when the check passes, 1
    when a check fails and 2 when the result is incomplete. All four bases pass, with
    every changed file attested. The acceptance gate and the pre-flight require a
    passed record made from the current transcript, base manifest and candidate
    patches (protocol v0.8 §16.5);
  * grading: a process-separated sandbox grader with trusted aggregation (harness
    `tc-harness/0.3.3` for the pilot). A later verification by model agents found a
    further path for forged results in the error handling of 0.3.2, which harness
    0.3.3 closes (D44). New runs use `tc-harness/0.3.5` (protocol v0.8 §16.1; D52). It
    differs from 0.3.3 in one respect: a failure while formatting or encoding a value
    or an exception for a result message never turns a successful call into a failed
    one and never leaves a call without a result. A result that JSON cannot encode
    (mixed or tuple keys, cycles, nesting deeper than 100 levels, dict subclasses whose
    methods raise) is converted by trusted code that calls no candidate method, with
    placeholders naming the type, and a last-resort message keeps `ok` and the error
    type. Two further behaviours apply only where 0.3.3 left a call without a result:
    a fallback for messages longer than the 199,921 characters the grader can read
    back, and a guarded output flush. Candidate code that runs while the result is
    formatted (a `__repr__` or `__str__`) can still end or stall the call. Harness
    0.3.4, which caught only exceptions raised in `repr()`, `str()` and traceback
    formatting, was never used for a run; protocol v0.7 §15.3 described it too broadly
    (D51). Within one call, code that the snippet runs still controls what that call
    reports, so every test of the process-separated verifiers asserts on a returned
    value, not only on success (the in-call limit; D3, D36, D40);
  * verifiers: specs (hashing, linting, freezing) and audit:v1;
  * evaluation: the evaluation matrix, and metrics (FA/FR, task-family cluster
    bootstrap, paired differences);
  * reporting: analysis (label policies, contradiction-aware contract coverage,
    mapper agreement, review queue, exploratory sensitivity), static HTML report,
    Harbor export and the CLI. A run graded with harness 0.3.4 or later, that is every
    new run, gets the reporting rules of protocol §15.7 and §16.6 (`tracecontract
    analyze --reporting-rules`, default `auto`): a per-family primary table, exact
    sign-flip p-values with their attainable floors, each distinct graded patch
    counted once, the oracle-gated view, solve rates and audit exclusions for fresh
    attempts, and bootstrap intervals in an appendix, marked as not inferential below
    10 families. The report names each run's populations and never pools them
    silently. The frozen pilot's analysis and report regenerate identically;
  * checks: same-code duplicate detection (`scripts/find_duplicates.py`), a stricter
    re-audit of the generator transcripts (`scripts/strict_reaudit.py`, D44), and a
    scan of the working tree and of every file version in the commits a push would
    send (`scripts/scan_tracked_files.py`). The scan is a manual step before each
    push, run with a private-marker file kept outside the repository; it is not a
    git hook (D44). With `--aidev-logins` it also checks for the 119 logins and names
    tied to the sampled AIDev pull requests, loaded in memory from the AIDev files,
    and for @handles in files under `tasks/` and `data/` (D48, D52);
  * fresh-agent tooling (protocol §15.4, §16.2; D52), not used yet:
    `scripts/make_agent_workspace.py --role fresh --variant u1|final` builds an
    isolated workspace whose instruction is U1, or U1 and U2, with each path of the old
    workspace replaced by the new workspace's, recorded in its manifest with the
    instruction's sha256; `tracecontract add-stratum-candidate` registers an attempt's
    final state as a stratum candidate without touching `task.json`; and
    `scripts/strict_reaudit.py --fresh` audits each attempt's tool inputs and outputs,
    with everything outside its workspace forbidden. Subagents' shell commands start
    in the study repository, so attempts must use absolute paths, and the audit
    excludes any attempt that does not;
  * records: the rule-based triage proposals of the four tasks are in the sidecars
    `tasks/<id>/triage.json`, and the four provenance records are restored byte for
    byte to `c5ede4c` (D52).
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
* **Protocol** v0.1 → v0.2 → v0.3 → v0.4 → v0.5 → v0.6 → v0.7 → v0.8
  (`experiments/protocol.md`). Each version was hashed and logged locally before the
  runs it governs (D15, D22, D32, D39, D40, D44, D48, D51); v0.7 and v0.8 govern only
  later runs and re-analyses and change nothing in the pilot. This is not a formal
  preregistration.
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
  * every table generated from records (`paper/make_tables.py`, which checks its
    arguments first and replaces the tables only after every one has been written;
    regenerating from `pilot-v0.3.3` with the documented command gives the tracked
    tables and ledger byte for byte);
  * an evidence ledger listing every table number with its source file;
  * compiles to 29 pages (2026-11-21, after the text updates for D47 to D52), with no
    LaTeX or biber warning and the four box warnings it had before; the full
    manuscript rebuild of round 4 is still to come.
* **Reviews by model agents** (Claude, the same model family; not human review):
  * an internal review with six lenses, whose skeptic agents checked findings until
    that stage was stopped for the final run;
  * a review of how each of its findings was resolved;
  * a final audit of every public claim and number (D40);
  * a verification of the fixes that followed them (D44), after which a second
    workflow corrected the text in six batches, each checked by a second agent (D45);
  * a final read-only verification of all of round 3, whose findings were fixed or
    disclosed (D46);
  * a re-audit of the repository against the original specification (D47);
  * a read-only verification of round 4 through four lenses (D51), whose findings
    were fixed (D52) or are tracked for later phases.

  Findings, verdicts and dispositions are in `docs/internal_review.md`.
* **Other documents:** annotation guide v0.4 (blinded review packet, D43, D44; its
  description of the acceptance gate corrected on 2026-11-21), data card, decision log
  D1–D52 (round 4: D47 onwards),
  submission-readiness notes (arXiv pages re-checked 2026-11-18), the
  ownership/defense notes, workflow and agent prompts (`experiments/prompts/`), and
  third-party licence notices (`THIRD_PARTY_LICENSES/`).
* **Round 4 (2026-11-21, in progress; D47 onwards):**
  * a re-audit against the specification by model agents (D47), protocol v0.7 (D48),
    a verification of round 4 by model agents and protocol v0.8 (D51), and the fixes
    from that verification (D52);
  * natural-data screening (D47, D48, D50). All 30 Trace Commons sessions were
    rejected, none reconstructable (`data/manifests/screening_natural.json`). In AIDev
    v5, the deterministic stages S1 to S8a leave 684 review comments on 190 pull
    requests (`data/manifests/screening_natural_aidev.json`), of which a random sample
    of 150 went to the model-judged stage S9
    (`data/manifests/screening_natural_aidev_s9.json`). Two model judges per comment
    found 31 that qualify: both say the comment asks for a behaviour change or reports
    a defect, that the first later commit touching the commented file addresses it,
    and that it can be checked offline. That is 20.7% of the sample (Wilson 95%
    interval 15.0% to 27.8%), from 25 pull requests in 14 repositories, or 20
    provisional families at most 2 per repository. 19 comments could not be judged,
    because their repositories could not be fetched here, and the judges disagreed on
    2, which are excluded. These are model proposals, not human coding; the 117
    failures are rows of `data/manifests/rejection_ledger.json`. Stage S10
    (replayability) is under way and has no recorded result yet;
  * harness `tc-harness/0.3.5` for new runs (above), and Harbor exporter
    `tc-harbor-export/0.3.0` (see Tested);
  * a frozen-input check, `scripts/verify_frozen_inputs.py`, which `pilot-v0.3.3`
    passes. It exempts only the git revision that `analysis.json` records and analysis
    code that changed since the run, as long as the analysis and report regenerate
    byte for byte; since D52 the provenance records' triage field is no longer exempt;
  * the reconstruction check and the enforced acceptance gate (above);
  * an exploratory re-analysis of `pilot-v0.3.3` and a draft precision plan, which is
    not adopted (D49);
  * the reliability re-grade of `pilot-v0.3.3` under harness 0.3.5 with three repeats
    (protocol §15.3, §16.1) started at 2026-11-21T07:22Z as run
    `pilot-v0.3.5-regrade`. It is in progress, and no result of it is reported here.

## Tested

* **373 tests at `a0542bb`**, 353 offline and 20 Docker (`pytest --collect-only -q`;
  no Docker run is needed to count them), all passing on 2026-11-21 (D52). The
  table-generator tests added since (`tests/test_make_tables.py`, 5 offline tests)
  bring the total to 378, and the 358 offline tests pass with them (2026-11-21). On
  2026-11-18, after the final run, there were 80 (63 offline, 17 Docker).
* **Offline tests:**
  * schemas, ingestion and evidence alignment;
  * supersession, contract validation and the acceptance gate;
  * patch policy, the leakage-check function (given an independent reference base;
    the task build called it without one, D47), and verifier lint/freeze (re-freezing
    refused, the check-list hash required);
  * trusted aggregation: missing, stale or crashed results never pass;
  * metrics, label policies, coverage and κ;
  * same-code duplicate detection and the Harbor export layout;
  * audit hold-out guard;
  * the blinded review packet and its merge (type checks, all-or-nothing writes,
    disagreement on violated requirements), and the strict re-audit (26 shell forms,
    attribution of scratch-directory reads);
  * round 4: the gate's review rules (each reviewer's latest decision, adjudication,
    re-review after `edit`) and its enforcement in `accept-task`, `evaluate` and the
    pre-flight, including the reconstruction record; the reconstruction check (v2)
    and differential tests against the transcript replay, which shares its Edit
    semantics; transcript replay, triage and its sidecars, the natural-data sanitiser,
    the AIDev funnel on a synthetic population, the manifest builder and the
    pseudonymiser for the later natural stages; the Harbor export's gate refusals and
    planted-reward grade paths, including cleanup on a bind-mounted directory; the
    frozen-input check and the exploratory re-analysis; agent workspaces (what each
    role may see, outside paths, the path substitution) and the fresh-attempt audit;
    the schema identifiers of §16.3, candidate strata and their registration,
    generation records, and D19 proposals for natural origins and strata; the
    reporting rules and pre-flight rules of new runs; and the table generator, whose
    `--help`, wrong arguments and failures leave every file in place.
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
  * a candidate `ast` module cannot forge the result of a snippet that raises (D44);
  * a candidate `__repr__` or `__str__` that fails while a result is formatted
    becomes a placeholder, and a result that cannot be encoded never changes the
    outcome (harness 0.3.5; 17 probe checks fail under 0.3.4 and pass under 0.3.5,
    D52);
  * the fresh-agent workspace wrappers run Python and pytest in the image, read-only
    and offline.
* **Characterisation probe:** the in-process repository-test baseline (B1) can be
  forged by an adversarial candidate. This is a documented limitation (D42).
* **Harbor:** export validated with oracle and no-op trials on a fixture task under
  harness 0.3.3 (Harbor 0.25.0; D35, D39, D40, D45). The outputs are recorded in
  `results/harbor_validation/tc-harness-0.3.3/` (and, for 0.3.2,
  `tc-harness-0.3.2/`). Exporter `tc-harbor-export/0.2.0` was validated on 2026-11-21
  under harness 0.3.3, with the same trials and two probes whose candidate code writes
  its own reward file, on a grader timeout and on a collection error: both ended
  without a reward, while under the earlier exporter both received reward 1.0
  (`results/harbor_validation/tc-harbor-export-0.2.0/`). Exporter
  `tc-harbor-export/0.3.0` was re-validated under harness 0.3.5 (D52): oracle 1.0, a
  wrong candidate 0.0, no-op 0.0, no reward on either probe, and no setuid or setgid
  file in the verifier image; the control run with the `c5ede4c` exporter still gives
  1.0 on both probes (`results/harbor_validation/tc-harbor-export-0.3.0/`).

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
  paper's central claim needs these labels. Human review alone cannot open the
  acceptance gate, because the documented procedure does not provide two of the
  things it requires (D51):
  * an `eligible` provenance record: no command sets it, and every record is
    `pending_review`;
  * initial-only and full-session contracts without unresolved or unreviewed inferred
    requirements: the gate checks every contract a task lists, these contracts hold
    unresolved requirements by design, and the blinded review packet covers only the
    reference contract.

  `tracecontract accept-task tasks/<id> --dry-run` lists every reason.
* **Natural data (SWE-chat).** The dataset's Hugging Face terms must be accepted by
  the owner, and the saved token fails authentication (`/api/whoami-v2` → 401). The
  two ungated, openly licensed sources need neither and were taken up for screening:
  all 30 Trace Commons sessions were rejected, and AIDev v5 pull-request review threads
  are in stage S10 (Completed, round 4). Whether pull-request review comments count as
  user corrections for the claim is an owner decision (D47).
* **Harbor `no-network` on this host.** Harbor rejected `no-network` on this host
  (the rejection was observed; its cause was not probed). Exported tasks declare
  `no-network`, and a `local-validation` variant is used only for oracle/no-op
  checks.
* **Owner decisions:**
  * the claim wording (D34);
  * confirmation of the acceptance-gate rules: each reviewer's latest decision counts,
    disagreements need an adjudicated review, and `edit` and `needs_discussion` block
    until a re-review accepts (DOCU-23; D51);
  * whether the gate should check review status on the condition contracts
    (initial-only and full-session), as it does now, or on the reference contract only;
  * whether review merges may write into the frozen candidate and contract files.
    `tracecontract merge-reviews` does so today: it appends labels to
    `tasks/<id>/candidates/*.json` and contract reviews to
    `tasks/<id>/contracts/reference.json`, which D47 freezes and the frozen-input check
    would report as modified. The alternative is sidecar files that the gate and the
    final-label rule read;
  * where the provenance review that sets a task's eligibility is recorded:
    `provenance.json` is frozen under D47, so a sidecar is the natural place;
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

* Any natural-data task, any second-annotator agreement, any second model family,
  and any downstream training experiment (no GPU and no approved spending).
* Any fresh-agent attempt or independent labeler (protocol §15.4, §15.5). Both are
  planned with subagents of the build session, which needs no spending.
