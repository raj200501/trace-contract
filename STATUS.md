# Status

Last updated: 2026-11-24 (UTC), after the run `natural-pr-v1` (decision log D76 to D78), the manuscript's restructure
(D79), a final fix round after a fresh verification (D80), the scanner's idiom rule for screened texts (D81) and a
round before human review (D82), with no new result: the review packet takes the fresh attempts, the abstract and
the stated scope of the evidence were revised, a downstream-training plan was written (not run), and the README and
the stale passages below were brought up to date from the records; then corrected after read-only reviews of commit
`f3ae845` by model agents (D83), again with no new result.
Nothing here is peer reviewed, and no human labels exist.

## Where the study stands

* **Lead result: fresh-agent attempts (`fresh-v1`, D61, D62).** 80 new agent attempts on the four controlled tasks,
  79 distinct graded patches, harness 0.3.5 with 3 repeats. Of the 40 attempts that saw only the first request, 27
  violate the correction. The initial-only verifiers (C1, C2) accept 24 of them; C3, C4, B2 and B1 accept none.
  This contrast is largely fixed by the design (D80): each violator breaks a requirement that only the correction
  states, which C1's contract lacks and C3's covers. By the study's procedure every model-written artifact, the labels
  included, comes from one model family of one provider; the corrections were scripted by the study's agent; and no
  candidate was optimised against a verifier, so these rates say nothing about a verifier used as a reward under
  optimisation (paper §8, items 3, 7 and 8).
  * The audit removed no false acceptance and added 6 false rejections (C4, CS-03).
  * B2 matches C3 and C4 on false acceptance.
  * All 34 of B1's false rejections come from tests the session agent added.
  * Labels are model proposals: the independent labeler, a model labeler of the same model family written from the
    same reference contract, agrees with D19 on 77 of 79 units. The study has four
    families, so no two-sided p below 0.125 is possible, and the result is descriptive.
* **Construction pilot (`pilot-v0.3.3`).** A development study since protocol v0.7. Its re-grade under harness 0.3.5
  gives the same outcome on all 240 pairs (D54).
* **Natural PR-review arm (`natural-pr-v1`).**
  * Screening is done for both samples: 31 of 150 and 91 of 534 comments qualify at S9 (model-judged; D63, D66).
  * S10 is done for the first sample, with 6 of 22 families accepted. The extension's S10 was stopped and is to be
    redone.
  * The recipe is fixed (D64, D65). Its phases P1 to P7 ran for all six families, each phase end committed
    (D70, D72, D75).
  * At the first audit, the natural reference fails 9 of the 12 audited verifiers. Five audits stay failing after
    three revisions (D27).
  * `natural-pr-v1` graded the six families, and its analysis is published in `results/runs/natural-pr-v1` (D76 to
    D78). The paper reports them as exploratory case studies, per family only. The extension's S10 is to be redone,
    for `natural-pr-v2`.
  * Read with the reference gate, the case studies say little about corrections (D80): C1 and C3 reject every
    candidate, their reference included, in NP-03, NP-05 and NP-18 (C4 too in NP-03, C1 alone in NP-20), and the
    repository tests pass the unchanged base in NP-03, NP-05, NP-19 and NP-20. In NP-04 and NP-19 the
    correction-aware verifiers accept near misses that break a correction requirement.
* **Manuscript (`paper/`).** Restructured under the restructure plan, with the natural section written from the run's
  cells into the template fixed before its analysis (D77; D79 records the integration), then revised after a fresh
  verification (D80): the lead contrast stated as largely fixed by construction, the shared source of the labels and
  the correction-aware verifiers stated, the natural case studies read family by family with the reference gate, the
  natural per-family detail moved unchanged to App. G, and four references on patch overfitting, test oracles and
  requirements change, each checked by model agents against its DOI's Crossref record (D80). Before the human review
  (D82) the abstract was rewritten around the planned measure, with the violators as denominator, and §8 gained the
  threat "No optimisation pressure". It compiles to 77 pages (the main text ends on page 23, where the references
  begin) with no `UNFILLED` marker, and every number in it is a generated macro with a ledger entry. A model reviewer,
  the one that checked D80's round, judged it close to a credible preprint as a methods or negative-results note (a
  workshop or an arXiv note, not a main track).
  Authors are a TODO for the human authors, who must review it before any submission.

## Where round 5 stopped, and how to resume

* **Usage cap.** After the reset of 2026-11-22, the owner asked the build session to keep going while using at most half
  of the plan's total usage. Round 5 used about 37M reported agent tokens against a plan of about 40M, and stops at the
  end of P4 for all six families (D68, D70).
* **To resume the natural arm** (round 5's plan, phases P5 to P7 and the run `natural-pr-v1`, is done for the first
  sample: D72, D75 to D78; protocol v0.12 §20.2, D71, gave each sample its own run; what remains is the extension's):
  1. Redo the extension's S10 (19 families, D66) and build its newly accepted families through D64's phases P1 to P7
     with `experiments/natural_workflow/natural_phase.js` (args `{task, phase, transcripts, config_b_model}`), running
     `scripts/record_phase_end.py` and committing the log alone after each phase (the P5 line pushed before P6, F7).
  2. Propose D19's labels, run the pre-flight and the run `natural-pr-v2`, which grades the extension's families on its
     own (§20.2, §20.3), then analyse and publish it.
  3. Before reading its results, read D70's observations: the natural reference often fails its own contract.
* **Done in round 5:** the natural analysis and the privacy tools (D69); the recipe's citations of D64; P1 to P4 for the
  six families (D70); a phase-end log with each line committed and pushed (D65).
* **Owner decisions pending.**
  * Deviation (i) and the other builder decisions of D64; D63's builder defaults; D69's privacy-tool defaults; D72;
    D73's reading of when D19 runs; D77's decision on the harness relay.
  * Whether the screening download records keep the fetched repositories' URLs before publication (D50, D63).
  * How the scan treats organisation accounts, before its `--aidev-logins` mode loads both S9 samples (D66).
  * Whether the pilot's frozen tables (`paper/generated/*.tex`, `evidence_ledger.md`) are re-frozen with the
    restructure's captions and names; until then they keep theirs, which the paper's Appendix F explains.
  * The builder decisions of D80: the move of the natural section's per-family detail, unchanged, to App. G; the
    model statement's wording; two template sentences changed where the records contradict them; and counting
    natural correction violators as the controlled tasks do.
  * The author line and the human authors' review of the paper before any submission; whether to name the models;
    and whether the committed controlled transcripts keep the model identifier in their raw records (D79, D80).
  * The human labels, and SWE-chat's access terms (below).
  * Whether to run the downstream-training plan at all, and its open decisions O1 to O8
    (`experiments/downstream_plan_v0.1-draft.md`, section 11; D82).
  * Whether standard-library import lines count as idioms in the scan's optional screening-texts mode, where one
    finding remains outside the push gate (D81).
  * Whether, where and when the repository is made public; the paper links none (paper §10).
  * The venue and the length: D80's reviewer placed the paper as a methods or negative-results note for a workshop or
    arXiv, not a main track; for arXiv, the primary category (`docs/submission_readiness.md`).

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
    and for @handles in files under `tasks/` and `data/` (D48, D52); since D69 it also runs with
    `--natural-texts data/natural/tasks`, which checks for the natural tasks' texts, code lines and repository
    names;
  * fresh-agent tooling (protocol §15.4, §16.2; D52), used for the 80 attempts of `fresh-v1` (D56, D57, D61):
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
* **Protocol** v0.1 → v0.2 → … → v0.8 → v0.9 → v0.10 → v0.11 → v0.12
  (`experiments/protocol.md`). Each version was hashed and logged locally before the
  runs it governs (D15, D22, D32, D39, D40, D44, D48, D51, D53, D57, D60, D71); v0.7
  onwards govern only later runs, re-analyses and the natural arm, and change nothing
  in the pilot. This is not a formal preregistration.
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
  bibliography checked by model agents on 2026-11-18. The claim is narrowed to a
  conjunction (D34), pending owner confirmation.
* **Manuscript draft** (`paper/`):
  * all sections drafted;
  * every table generated from records (`paper/make_tables.py`, which checks its
    arguments first and replaces the tables only after every one has been written;
    regenerating from `pilot-v0.3.3` with the documented command gives the tracked
    tables and ledger byte for byte);
  * an evidence ledger listing every table number with its source file, and, since the restructure (D79), every
    number in the text a generated macro with a ledger entry, which `paper/check_numbers.py` checks (22 files, no
    number outside a macro, 2026-11-23);
  * compiles to 77 pages (the main text ends on page 23, where the references begin), with no overfull box, no
    undefined reference or citation and no LaTeX warning (rebuilt on 2026-11-24 after the corrections that followed
    the reviews of `f3ae845`; D80 and D82 recorded 76 pages, D82 with the references from page 23). The 29 pages of
    2026-11-21 were the draft before the rebuild around `fresh-v1` (D66) and the restructure (D79).
* **Reviews by model agents** (of the build session's model family, one model family of one provider; not human
  review):
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
    were fixed (D52) or are tracked for later phases;
  * the two-lens reviews of D74 and D77; the three-lens reviews of D79; the accuracy and venue reviews of D80 and the
    check of its fix round; the reviewer of D81; D82's two reviewers (the round's parts, and the downstream plan); and
    the four-lens read-only review of `f3ae845` and the check of its fix round (D83).

  Findings, verdicts and dispositions of the reviews through D46 are in `docs/internal_review.md`; those of D47 and
  later are in their decision-log entries.
* **Other documents:** annotation guide v0.4 (blinded review packet, D43, D44; its
  description of the acceptance gate corrected on 2026-11-21, and its section on candidate strata in the packet
  added on 2026-11-24, D82), data card, decision log
  D1–D83 (round 4: D47 to D52; the later rounds: D53 onwards), the downstream-training plan
  (`experiments/downstream_plan_v0.1-draft.md`: a draft, not run and not adopted; D82),
  submission-readiness notes (arXiv pages re-checked 2026-11-23), the
  ownership/defense notes, workflow and agent prompts (`experiments/prompts/`), and
  third-party licence notices (`THIRD_PARTY_LICENSES/`).
* **Round 4 (2026-11-21; D47 to D52, with the re-grade of D54):**
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
    (replayability) later accepted 6 of the first sample's 22 families (D59), which `natural-pr-v1` graded (D76 to
    D78);
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
    (protocol §15.3, §16.1), run `pilot-v0.3.5-regrade` (2026-11-21, 07:21:53 to 08:18:38 UTC). It agrees with
    `pilot-v0.3.3` on all 240 pairs, in reward and in exact outcome, with no unresolved outcome (D54).

## Tested

* **1,464 tests** (D82), 1,444 offline and 20 Docker (`.venv/bin/python -m pytest --collect-only -q`). Counting them
  needs a reachable Docker daemon: without one, `tests/test_sandbox_isolation.py` is skipped whole at collection, and
  the command lists 1,445. This round added 90 offline tests: 17 for the review packet's strata
  (`tests/test_review_packet_strata.py`) and 73 for the downstream plan's data step
  (`tests/test_build_training_selection.py`). On 2026-11-24 the build checkout, which holds the natural data, passed
  all 1,444 offline tests and the 20 Docker tests. A clone with the base snapshots built and without the git-ignored
  `data/natural/` passed 1,435 offline tests, and 9 skipped, all for want of the natural data; before the snapshots
  are built, 14 more skip. At `2daa725` there were 1,374 (1,354 offline; D81). In a checkout under `/tmp`, one
  location test of `tests/test_agent_workspace.py` failed, because the rule that refuses roots around the checkout
  itself refused `/tmp` before the session-directory rule the test expects; the test now puts the checkout beside
  its fixture study for that check (2026-11-23). Earlier counts: 373 at `a0542bb` (353 offline, 20 Docker), all
  passing on 2026-11-21 (D52), and 378 with the first table-generator tests; on 2026-11-18, after the final pilot
  run, 80 (63 offline, 17 Docker).
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
    disagreement on violated requirements; with candidate strata, their blinding, the refusals before anything is
    written and the merge into the stratum files, D82), and the strict re-audit (26 shell forms,
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

* **Human annotation.** Contracts, the 32 held-out candidates and the 79 analysed fresh attempts need review by two
  qualified human reviewers per task. A coordinator builds the blinded review packet
  (`tracecontract review-packet`) and keeps its key. The reviewers work from the
  packet only, following `docs/annotation_guide.md`, and `tracecontract
  merge-reviews` merges their labels once every task has two complete reviews. The
  queue (`tasks/*/labels/review_queue.json`) is opened only after the merge. The
  paper's central claim needs these labels. The analysis of `fresh-v1` queues all 79 analysed attempts for human
  review (`labels.<task>.strata.fresh-v1.review_queue` in its `analysis.json`), as the paper's App. H says. The
  attempts are stratum candidates (`tasks/*/strata/fresh-v1/`, 20 per task), and
  `tracecontract review-packet ... --strata fresh-v1` puts these 79 among each task's own held-out candidates (8 per
  task, 32 in all), blinded as they are, and leaves out the excluded CS-02-fresh-A-final-1 (annotation guide,
  section 2; D82). On the recorded tasks such a packet holds 110 items for 111 candidates (28, 27, 28 and 27 items
  per task), because two CS-04 pilot candidates have the same diff and share an id. `merge-reviews` appends the
  attempts' labels to their files in the stratum (owner decisions, below). No human label exists yet. Human review
  alone cannot open the acceptance gate, because the documented procedure does not provide two of the things it
  requires (D51):
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
  gave six families, built and graded in `natural-pr-v1` as exploratory case studies (D75 to D78); the extension's
  S10 is to be redone, for `natural-pr-v2`. Whether pull-request review comments count as
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
    would report as modified. It also appends the fresh attempts' labels to their files in the stratum,
    `tasks/<id>/strata/fresh-v1/candidates/*.json`, whose sha256 hashes the analysis of `fresh-v1` records among its
    inputs (`meta.inputs.files_sha256` in its `analysis.json`, all 80 attempt files), so after a merge they no longer
    match the recorded analysis; the frozen-input check does not read the strata. The alternative is sidecar files
    that the gate and the final-label rule read;
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

* Any human label, and so any agreement between human annotators.
* Any second model family, for the agents, the generators or the labelers.
* Any downstream training experiment (no GPU and no approved spending). A plan for one, not run and not adopted, is
  in `experiments/downstream_plan_v0.1-draft.md`, with its tested data step (`scripts/build_training_selection.py`;
  D82).
* The extension's S10 replay, its families and their run, `natural-pr-v2` (protocol §20).

The fresh-agent attempts and the independent labeler, listed here before, have run: `fresh-v1` (D61, D62) and the
labelers of protocol §15.5 (D55, D58). So have natural-data tasks: the six families of `natural-pr-v1` (D75 to D78).
