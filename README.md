# TraceContract

**Do the verifiers of coding tasks rebuilt from agent sessions reward what the user actually wanted?** When a coding
task is reconstructed from an agent session, later user corrections change what counts as a correct solution, for
example "actually, keep the old default" or "step=0 must raise". A verifier built from an incomplete account of those
corrections can go wrong in two ways:

* **false acceptance (FA):** it accepts solutions the user rejected;
* **false rejection (FR):** it rejects solutions the user would accept.

TraceContract measures both. It generates verifiers from the first request or from the whole session, freezes them,
and grades them in a sandbox on held-out agent patches, against labels from a pre-specified rule.

> **Status: research prototype; an automated study with model-proposed labels; not peer reviewed.**
> * **No human labels exist.** Every rate rests on labels proposed by a pre-specified rule (D19; "D*n*" is entry *n*
>   of the [decision log](docs/decision_log.md)). On the fresh attempts, a second model labeler, of the same model
>   family and written from the same reference contract, agrees with it on 77 of 79 units.
> * **Controlled tasks.** The verifier results come from four task families: real agent sessions whose user turns,
>   the corrections included, the study scripted. They are not natural user traffic.
> * **Natural case studies.** Six pull-request-review families from AIDev v5 were built and graded (run
>   `natural-pr-v1`) and are reported as exploratory case studies, family by family.
> * **Manuscript.** [`paper/`](paper/README.md) builds a 77-page preprint (main text about 23 pages) by Raj Kashikar
>   (Cornell University), not peer reviewed. Current state and decisions: [STATUS.md](STATUS.md).

## In short

**What was done.** The study starts from four recorded agent sessions (task families CS-01 to CS-04), each with a
scripted correction. One frozen procedure generated verifiers from the first request only (C1) or from the whole
session (C3), each also with a predefined audit that may revise the tests (C2, C4). Two baselines: the repository's
tests at the session's final state (B1), and tests that a model wrote from the whole transcript, with no contract
(B2). Fresh agents, in two configurations (A and B), then made 80 attempts at the four tasks, given the first request
alone or with the correction. Every condition graded every attempt three times in a Docker sandbox
(process-separated for all but B1); after one exclusion by its audit, 79 distinct patches are analysed, 29 invalid
and 50 valid (run `fresh-v1`).

**What was found** (descriptive; four families; model-proposed labels):

1. **Withholding the correction yields agent-made negatives.** Of the 40 attempts that saw only the first request, 27
   violate the correction; no generator wrote them. Every analysed attempt that saw the correction is valid (39 of
   39).
2. **First-request verifiers accept those violations and whole-session verifiers do not, largely by construction.**
   C1 accepts 24 of the 27 violators, C3 none. Each violator breaks a requirement that only the correction states: C1's
   contract lacks it, C3's has it, and the reference checks behind the labels were written from a contract that states
   it.
3. **A reference gate misses silent loss** (a post hoc reading of two families; which families show it follows largely
   from what their corrections do: C1 passes the reference wherever the correction only adds requirements, CS-02 to
   CS-04, and fails it in CS-01, whose correction retracts a requirement C1 encodes). In CS-03 and CS-04, the two of
   those families with correction violators, C1 passes the reference solution, so a gate that keeps only verifiers
   passing their reference keeps it, yet it accepts 14 of the 17 violators there. None of its checks maps to the
   requirement those violators break, as its generator's template asks: it tests its contract and is told not to
   over-fit the reference diff it is given. Where the correction retracts part of the request (CS-01), C1 fails 12 of
   its 14 checks on the reference, and a gate catches it.
4. **Repository tests at the final state cut both ways.** They reject 34 of the 50 valid attempts, all through 40
   checks that the session agent added. The base commit's own tests reject none, but alone they pass 17 of the 29
   invalid attempts. Both follow from the label rule, whose regression norm the base tests are; what the run measures
   is that the 40 added checks reject 34 valid attempts and catch those 17.
5. **More machinery did not help.** On the fresh attempts the audit removed no false acceptance and raised false
   rejection from 0/50 (C3) to 6/50 (C4). The transcript-only baseline B2 matched the correction-aware contracts
   (C3, C4) on false acceptance (2/29 each).
6. **The natural case studies are mostly uninformative about corrections.** In six pull-request-review families,
   where a reviewer's comment plays the correction (run `natural-pr-v1`), C1 and C3 reject every candidate, the
   addressing commit and the valid alternatives included, in NP-03, NP-05 and NP-18, and the repository tests pass the
   unchanged base in NP-03, NP-05, NP-19 and NP-20. In NP-04 and NP-19 the correction-aware verifiers accept near
   misses that break a correction requirement.

**What this does not show.** By the study's procedure, one model family of one provider wrote the scenarios, the
verifiers and the labels (for several roles no record holds the model's identifier, so the release cannot confirm
this), and the reference checks share inputs with the correction-aware verifiers, so C3's zero is partly agreement
between renderings of the same requirements. The 27 violators form only 4 distinct outcome patterns within their
families. With four families no exact sign-flip test can go below p = 0.0625 one-sided, and none of the 14 planned
comparisons reaches that floor. No candidate was optimised against a verifier, so these false-acceptance rates,
including the 0 of 27 violators that C3, C4 and B2 accept, say nothing about a verifier used as a reward under
optimisation (paper §8). C1 is not a pipeline in use: no cited pipeline builds a verifier from a contract of the first
request (paper §6, Positioning); the baselines tied to practice that paper §7 lists (a first-request suite gated on
the pre-correction state, a full-session task statement with test refinement, an LLM judge) were not built; and B3,
which keeps tests from the first request and the reference diff only if they fail on the base and pass on the
reference, ran in the natural arm only. These numbers describe these tasks; they are not evidence of an effect beyond
them. See [Limitations](#limitations).

Sources: `results/runs/fresh-v1/analysis.md`, `results/runs/natural-pr-v1/analysis.md`, and the paper's generated
numbers (`paper/generated/*/numbers.tex`, each value listed with its file and field in `paper/evidence_ledger_*.md`);
paper Sections 3 and 5.

## What is in the repository

* **The pipeline** (`src/tracecontract/`, command `tracecontract`): session ingestion and sanitisation; contracts whose
  requirements carry a status (explicit, inferred, superseded or unresolved), the turn that introduced them and exact
  quotes; verifier generation, linting, freezing and the audit; candidate pools and strata; label proposals; an
  analysis with per-family tables and exact sign-flip tests; static HTML reports; and an acceptance gate for tasks.
* **Sandboxed grading** (`tc-harness/0.3.5`). Hidden tests run in a trusted grader; candidate code runs only as an
  unprivileged UID unique to its container and cannot read the tests or write the results; per-call results are
  authenticated, and the host recomputes outcomes. Docker probes test the boundary, with a regression probe for each
  path to a forged result that the study's reviews found (a module shadowing the standard library, an `encodings`
  package loaded at interpreter start, an `ast.py` loaded while an exception is formatted).
* **Harbor export** (`tc-harbor-export/0.3.0`), validated with a pinned Harbor 0.25.0: the oracle gets reward 1.0, a
  wrong candidate and a no-op 0.0, and two probes that plant their own reward file get none, while the earlier
  exporter (`c5ede4c`) gives them 1.0 (`results/harbor_validation/tc-harbor-export-0.3.0/`).
* **An evidence ledger.** Every number in the manuscript's text is a generated macro and every table is generated
  from recorded files; each value has a ledger entry naming the file and field it comes from
  (`paper/evidence_ledger*.md`), and `paper/check_numbers.py` fails on any digit or count word outside a macro.
* **Byte-for-byte regeneration.** From the recorded controlled runs, the analyses, reports, tables, figures and
  ledgers regenerate byte for byte, apart from the git revision and code hashes that an `analysis.json` records; the
  natural run's tables regenerate from its published `analysis.json` (see Reproduce in full).
* **Privacy scanning** (`scripts/scan_tracked_files.py`): the working tree and every file version a push would send
  are checked for credentials, session-local paths, e-mail addresses, private markers and, for the natural arm, the
  logins tied to the sampled pull requests, the natural tasks' thread texts, their repositories' names and their
  upstream code lines. The natural run is published as identifiers, hashes and outcomes only; the screening records
  hold more (`docs/data_card.md`, Personal information).
* **A downstream-training plan, not run** (`experiments/downstream_plan_v0.1-draft.md`): rejection-sampling
  fine-tuning and then RL, with first-request against whole-session verifiers as the data filters and rewards,
  matched budgets, held-out repositories and human labels as the judge, and why the present families cannot support
  it. Its tested data step (`scripts/build_training_selection.py`, `configs/downstream/`) lists what each verifier
  would admit from the recorded fresh attempts (`results/analyses/fresh-v1-training-selection/`): a post hoc
  illustration that measures no training value.
* **Tests:** 1,465 (1,445 offline, 20 Docker). On 2026-11-25 all of them passed in the build checkout; in a clone
  with the base snapshots built, 9 offline tests skip, since they need the unpublished natural data; in a fresh clone,
  before the snapshots are built, 14 more skip.
* **Records:** a protocol hashed and logged locally before each run it governs (`experiments/protocol.md`; not a
  formal preregistration), a decision log (D1 to D84), run manifests with code revisions, image identifiers and
  hashes, and the prompts that produced the model-written artifacts (`experiments/prompts/`).

## Quick start

Linux, Python 3.13, [uv](https://docs.astral.sh/uv/), git and a running Docker daemon, with network access to
github.com, Docker Hub and PyPI ([all requirements](#reproduce-in-full)).

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -c constraints.txt -e ".[dev,data]"
for t in CS-01 CS-02 CS-03 CS-04; do .venv/bin/tracecontract snapshot tasks/$t; done   # base snapshots from github.com
.venv/bin/python -m pytest -q -m "not docker"    # the offline suite, about 3 to 4 minutes
.venv/bin/tracecontract grade tasks/CS-01 full_audited CS-01-pre-correction            # one verifier on one candidate, in the sandbox
.venv/bin/python paper/make_tables.py --fresh results/runs/fresh-v1 --regrade results/runs/pilot-v0.3.5-regrade --natural
.venv/bin/python paper/check_numbers.py          # no number in the paper's text outside a generated macro
cd paper && latexmk -pdf main.tex                # the manuscript
```

`constraints.txt` pins the package versions of the environment in which the checks ran; without
`-c constraints.txt`, the install takes the newest versions that `pyproject.toml` allows. In the offline suite, 9
tests skip: they need the git-ignored natural data (`data/natural/`), which is not published. The grade reports `task_failure` with reward 0.0 (C4 fails all 14 of its checks on the agent's
pre-correction state of CS-01), as `pilot-v0.3.3` recorded; the first `grade` builds the sandbox images, which needs
Docker Hub and PyPI. The table generator rewrites `paper/generated/fresh/` and `paper/generated/natural/` byte for
byte, so `git status` stays empty.

## Lessons for building verifiers from traces

What the study supports, on its four controlled families and six natural case studies, with model-proposed labels.
Each item names its evidence and its caveat; section, table and figure numbers refer to the draft that
`paper/main.tex` builds.

1. **Grade every generated verifier on the reference solution and on a no-op before you use it.** A verifier that
   fails the reference is wrong about the task, and one that gives every candidate the same outcome cannot tell
   candidates apart. *Evidence:* CS-01's first-request verifier fails 12 of its 14 checks on the reference, exactly those that encode
   the request the correction retracted (§3.1, Figure 1). The audit of its audited twin (C2) failed with the
   reference not passing, and C2 was frozen as it stood (§3.2; D27). In the natural run the reference gate drops C1
   in NP-03, NP-05, NP-18, NP-19 and NP-20 and C3 in NP-03, NP-05, NP-18 and NP-19, and the repository tests pass
   every candidate, the unchanged base included, in NP-03, NP-05, NP-19 and NP-20 (§5, §7; Table 45 in App. G).
   *Caveat:* in the natural arm the reference is the addressing commit, not an oracle, and a gate settles every
   disagreement in the reference's favour.
2. **Passing the reference is not coverage: check that the verifier tests what the correction added.** *Evidence:* in
   CS-03 and CS-04 the first-request verifier passes the reference, so a gate keeps it, and it accepts 14 of the 17
   correction violators; none of its checks (14 in CS-03, 12 in CS-04) maps to the requirement they break, under
   either of two model mappers (§3.1, Table 4). Mapping each check to a requirement list that includes the
   correction, as the study's mappers do against the reference contract (Table 11 in App. D), shows that gap before
   any candidate is graded. *Caveat:* a post hoc reading of the secondary, reference-gated view, in two families.
3. **Rebuild the task from the whole session, not the first request.** *Evidence:* verifiers from the first request
   (C1, which no cited pipeline builds as such) accept 24 of the 27 agent-made violators, verifiers from the whole
   session none (§3.1). *Caveat:* largely fixed by
   construction, and the labels' reference checks share a model family, the reference diff and the requirements with
   the whole-session verifiers. An initial-only contract can already hold the correction: CS-02's covers everything
   its correction adds.
4. **Keep the agent's added tests apart from the repository's own when a final-state suite is the verifier.**
   *Evidence:* at the reference state the repository tests reject 34 of the 50 valid attempts, all through the 40
   checks the session agent added; the base commit's 2,179 checks reject none, but alone pass 17 of the 29 invalid
   attempts (§3.3; Table 16 in App. E). *Caveat:* the base tests are the label rule's regression norm, so under that
   rule they cannot reject a valid attempt.
5. **Do not expect an audit that attacks a verifier from its own contract to add a missing requirement, and check
   what its revisions pin down.** *Evidence:* the audit changed no outcome of the first-request verifier (C2 equals
   C1 on every attempt); in CS-03, C4's one revision added 2 checks that fix answers the contracts leave open, which
   caused 6 false rejections (§3.2; D62). In the construction pilot it changed one held-out outcome (§4). *Caveat:*
   one audit design (`audit:v1`).
6. **Compare against a plain transcript-to-tests baseline.** *Evidence:* B2, written from the transcript without a
   contract, matched the correction-aware contracts (C3, C4) on false acceptance (2/29) with 2/50 false rejections
   (§3.2).
   *Caveat:* four families cannot show equivalence, and no scenario has several or conflicting corrections, where
   contracts might matter most (§7).
7. **Withhold the correction to get agent-made negatives, and count distinct behaviours, not attempts.** *Evidence:*
   fresh agents given only the first request made 27 correction violators in 40 attempts, which form 4 outcome
   patterns within their families (§1, §3.1). *Caveat:* these tasks are easy: every analysed attempt that saw the
   correction solved its task.
8. **Treat the grader as an attack surface.** *Evidence:* the study's reviews found paths by which candidate code
   could forge a grade (a module shadowing the standard library, an `encodings` package, an `ast.py` on the error
   path), and Harbor's world-writable reward directory gave two reward-planting probes 1.0 under the earlier exporter.
   Each path now has a regression probe (the grader paths: App. C and `results/runs/README.md`; the reward directory:
   App. C, D51, D52 and `results/harbor_validation/tc-harbor-export-0.3.0/summary.json`). *Caveat:*
   within one call, code that the snippet runs still controls what that call reports, and the in-process B1 baseline
   can be forged.

## Limitations

* **No human labels.** The labels are rule-based model proposals (D19), and an independent model check disputes
  some of them. The analysis queues all 79 analysed fresh attempts for human review, and
  `tracecontract review-packet ... --strata fresh-v1` puts them in the blinded packet among each task's own held-out
  candidates, blinded as they are, and leaves out the excluded CS-02-fresh-A-final-1. On the recorded tasks such a
  packet holds 110 items for 111 candidates (the pilot's 32 and the 79 attempts), because two CS-04 pilot candidates
  have the same diff and share an id. `tracecontract merge-reviews` appends the attempts' labels to their files in
  the stratum (`tasks/*/strata/fresh-v1/candidates/`). No human label exists yet.
* **The lead results come from controlled sessions,** with scripted corrections designed by the study; the natural
  arm adds case studies only. `fresh-v1` reuses the pilot's four families and frozen verifiers, and was designed
  after the pilot's results were known: it adds held-out candidates, not families.
* **One model family.** By the study's procedure, one model family produced the scenarios and reference contracts
  that define the labels (written by the study's AI agent, the same model as the session agent), the sessions,
  contracts, verifiers, candidates, label proposals, checks and both requirement mappers. For several roles no record
  holds the model's identifier, so the release cannot confirm this (paper Table 1).
* **Four task families,** so all rates are descriptive.
* **Repository-test baseline (B1):** it imports candidate code into its reporting process, so an adversarial candidate
  can forge its report. A characterisation probe in the test suite shows this. B1 also includes tests that the session
  agent wrote.
* **Natural data.** SWE-chat is blocked on its access terms, which only the owner can accept (D4). Two ungated, openly
  licensed sources were taken up for screening as separate populations (D47):
  * Trace Commons: all 30 sessions were screened and rejected, none reconstructable;
  * AIDev v5 pull-request review threads: six families were built and graded in `natural-pr-v1` (D75 to D78) and are
    reported as exploratory case studies, with no pooled rate. A reviewer's comment is not an in-session correction
    from the requester, and the reference is the addressing commit, not an oracle. The extension's replay (S10) was
    stopped at a usage limit and is to be redone, with its own run, `natural-pr-v2` (protocol §20).
  * The committed scan's `--aidev-logins` mode loads the logins connected to the first S9 sample only. A one-off scan
    with both samples found no person's login (D66); the scan keeps that scope until the extension's S10 is redone,
    and loading the extension's logins then needs a rule for organisation accounts (D66, D84).
* **No task passes the acceptance gate** (`tracecontract accept-task tasks/<id> --dry-run`), so every run is an
  automated pilot (`--pilot`).
* **The held-out discipline is imperfect,** and each departure is disclosed in decision log D31, D37, D40, D41 and D44:
  * generators and reference-check writers ran as the same user in the repository checkout, so separation rested on
    instructions and on audits of their tool inputs (tool outputs showed held-out file names to some agents);
  * the held-out generators, the reference-check writers and their reviewers shared the build session's scratch
    directory, which also held other agents' working files and some material derived from candidates. The first
    audit treated only its sealed subfolders as forbidden. A stricter re-audit, which treats the whole directory as
    forbidden, found no read of candidate, verifier or sealed material. Some listings showed file names (`git status`
    among them, which named held-out CS-02 candidate files), and one reviewer of CS-02's checks read all of another
    reviewer's test runner there, which holds no candidate or other verifier material (`strict_reaudit` in
    `tasks/*/labels/generator_audit.json`; D44, D46);
  * near-miss generators had and ran B1's tests (D37), so B1's outcomes on near misses are not blind to construction;
  * three held-out candidates duplicate a development attack;
  * the reference checks were written while the pools were being generated; CS-03's were frozen before its pool was
    registered, and CS-02's were revised mostly after its pool was complete;
  * the prompts of 2026-11-18 (CS-01's near misses, and all of CS-02's held-out candidates and reference checks)
    differ from the earlier CS-03/CS-04 prompts, which CS-01's alternatives and reference checks also used;
  * CS-04's B1 was re-selected after its pool existed;
  * the hash of each scored check list was added only after the run `pilot-v0.3`.
* **The fresh attempts' context held harness material:** an environment block naming the study repository and the
  build session's scratch directory, and the build session's task-list reminders (How the measurement works). It holds
  no reference, verifier, candidate or label, but it names the study repository, so an attempt may infer that it is
  part of a study (paper §8, item 5).
* **No training experiment and no optimisation pressure.** No training was run, and nothing here claims a model
  improvement. No candidate was optimised against a verifier, so the false-acceptance rates say nothing about a
  verifier used as a reward under optimisation, where a policy can search out what the verifier does not check
  (paper §8). A plan for such an experiment, not run, is in `experiments/downstream_plan_v0.1-draft.md`.

## Results in detail

### Fresh-agent attempts (`fresh-v1`), the lead result

Run `results/runs/fresh-v1` (decision log D61, D62):
* 80 new agent attempts on the four controlled tasks, in two agent configurations, each given the first request only
  (`u1`) or the first request with its correction (`final`), 5 attempts per cell;
* 1 attempt excluded after the reviewed audit, so 79 distinct graded patches: 29 invalid, 50 valid (D19);
* 672 pairs under harness 0.3.5, every pair graded 3 times, no unresolved outcome.

The analysis is `results/runs/fresh-v1/analysis.md`; the paper's Section 3 reports it, with the per-family table as
its primary display (Table 3; Figure 2, `paper/generated/figures/fresh_fa_fr_by_family.pdf`).

| Condition | FA per family: CS-01, CS-02, CS-03, CS-04 | FA pooled | FR per family: CS-01, CS-02, CS-03, CS-04 | FR pooled |
| --- | --- | --- | --- | --- |
| C1 initial-only, plain | 10/10, 0/2, 4/7, 10/10 | 24/29 | 10/10, 0/17, 3/13, 0/10 | 13/50 |
| C2 initial-only, audited | 10/10, 0/2, 4/7, 10/10 | 24/29 | 10/10, 0/17, 3/13, 0/10 | 13/50 |
| C3 correction-aware, plain | 0/10, 2/2, 0/7, 0/10 | 2/29 | 0/10, 0/17, 0/13, 0/10 | 0/50 |
| C4 correction-aware, audited | 0/10, 2/2, 0/7, 0/10 | 2/29 | 0/10, 0/17, 6/13, 0/10 | 6/50 |
| B2 full-session LLM | 0/10, 2/2, 0/7, 0/10 | 2/29 | 0/10, 0/17, 2/13, 0/10 | 2/50 |
| B1 repository tests (reference state) | 0/10, 0/2, 0/7, 0/10 | 0/29 | 8/10, 17/17, 9/13, 0/10 | 34/50 |

How to read this:

* **Initial-only verifiers accept what the correction ruled out.** Of the 40 `u1` attempts, 27 violate the
  correction. C1 and C2 accept 24 of them; C3, C4, B2 and B1 accept none.
* **The 2/29 of C3, C4 and B2** are two CS-02 attempts that are invalid only through the regression norm: they fail a
  base test that asserts on a private attribute both removed, and pass all 28 reference checks. The independent
  labeler calls both valid. No CS-02 attempt violates the correction (D62).
* **CS-01, a loud inversion.** C1 and C2 encode the request that the correction retracted. They fail the reference on
  12 of their 14 checks, which gives 10 of C1's 24 false acceptances and 10 of its 13 false rejections. In the
  reference-gated view, which drops C1 in CS-01, C1 has FA 14/19 and FR 3/40 (D62).
* **CS-03 and CS-04, a silent loss.** C1 passes both references and accepts 14 of their 17 correction violators,
  against 0 of 17 for C3; no C1 check maps to the requirement those violators break (paper §3.1, Table 4).
* **The tests of the proposed machinery are null or negative.**
  * The audit removed no false acceptance. It added 6 false rejections, all in CS-03, through the 2 checks that C4's
    one revision added, which fix answers the contracts leave open.
  * The full-session LLM baseline (B2) matches C3 and C4 on false acceptance.
* **B1's false rejections come from the session agent's tests.** All 34 come from the 40 checks that the session agent
  added to the reference state. The base commit's tests reject none, and alone they would accept 17 of the 29 invalid
  attempts. Both follow from the label rule, whose regression norm the base tests are; what the run measures is that
  the 40 added checks reject 34 valid attempts and catch those 17.
* **The effect is concentrated and largely fixed by construction.** Each violator breaks a requirement that only the
  correction states; C1's contract lacks it and C3's covers it, and the reference checks behind the labels were
  written from a reference contract that states it (paper, Section 3.1). The 27 violators form 4 distinct outcome
  patterns within their families, and C1's false acceptances come from three families (CS-01, CS-03, CS-04).
* **Robustness.**
  * The independent labeler agrees with D19 on 77 of 79 units (κ 0.94); its 2 disagreements are the CS-02 attempts
    above. Under its labels C1 accepts 24 of 27 invalid attempts and C3 none.
  * Excluding all 26 attempts that the automated audit flagged (`analysis_sensitivity.md`) leaves the ordering: C1
    accepts 18 of the 20 correction violators left and C3 none (paper §3.4); counting all 21 invalid units left, C1
    accepts 18 and C3 1 (D61).
* **Uncertainty.** With four families no exact sign-flip p below 0.0625 one-sided or 0.125 two-sided is possible, and
  none of the 14 planned comparisons reaches that floor. C1 against C3 on false acceptance has one-sided p = 0.125,
  because CS-02 differs in the other direction; C1 against C3 and B1 against C4 on false rejection sit at their
  conditional floors (0.25 and 0.125), which the families with no difference set.

  **These are descriptive numbers on model-proposed labels, not evidence of an effect beyond these tasks.**

### Two worked examples (paper Figure 1)

Both are from `fresh-v1`; the quotes are exact excerpts of the scenario files (`data/controlled/scenarios/`).

* **CS-04, silent loss** (`more-itertools`). The first request asks to *add a `step` option to
  more_itertools.consecutive_groups*; the correction adds, among other requirements, that *step=0 should raise a
  ValueError rather than doing something weird*. C1 passes the reference, but none of its 12 checks maps to that
  requirement, and it accepts all 10 first-request attempts, each of which breaks it. C3 accepts none of them.
* **CS-01, loud inversion** (`humanize`). The first request: *I'd like it to drop a trailing ".0" so those read "3 MB"
  and "1 KiB"*. The correction: *Please keep the default output exactly as it was before*; trimming becomes opt-in
  through `strip_trailing_zero`, and custom formats, even positional ones, must not change. 12 of C1's 14 checks
  encode the retracted request, and all 12 fail on the reference. C1 accepts all 10 violators and rejects all 10 valid
  attempts; C3 accepts none of the violators. A gate on the reference drops C1 here. The construction pilot showed the
  same on the session agent's own pre-correction state: both initial-only verifiers (C1, C2) accept it and reject both
  valid alternatives and the reference solution, and all correction-aware conditions reject it and accept the
  alternatives (`pilot-v0.3.3`).

### Natural PR-review case studies (`natural-pr-v1`)

* **Screening.** 684 review comments pass the deterministic stages S1 to S8a. At stage S9, model judges find that 31
  of 150 comments (first sample) and 91 of 534 (extension) qualify (D48, D50, D63, D66).
* **Replay.** At S10, 6 of the first sample's 22 families are accepted: NP-03, NP-04, NP-05, NP-18, NP-19 and NP-20.
  The extension's replay was stopped at a usage limit and is to be redone (D66, D75).
* **Construction.** The recipe is fixed (D64, D65). For all six families it built the three contracts and the seven
  frozen verifiers (phases P1 to P4; D70), then the reference checks, the labeler, the held-out pool, the mappers and
  the audits (P5 to P7; D72, D75).
  * At its first audit, the natural reference fails 9 of the 12 audited verifiers. C1 fails it in five families, C3
    in four.
  * The audit's revisers loosened checks toward the reference, and five audits stay failing after three revisions.
* **Graded (D76 to D78).** The run `natural-pr-v1` graded 432 pairs, each 3 times, with no unresolved outcome. Its
  analysis and its id-and-outcome release are in `results/runs/natural-pr-v1`. The paper reports the six families as
  exploratory case studies, in per-family tables, with no pooled rate, interval, p-value or total; all labels are model
  proposals.
  * Read with the reference gate, the case studies are mostly uninformative about corrections (D80): C1 and C3 reject
    every candidate, their reference and the valid alternatives included, in NP-03, NP-05 and NP-18 (C4 too in NP-03,
    C1 alone in NP-20), and the repository tests pass the unchanged base in NP-03, NP-05, NP-19 and NP-20.
  * In NP-04 and NP-19 the correction-aware verifiers accept near misses that the label rule marks invalid for
    breaking a correction requirement; of these, only NP-04's eval-nm-2 breaks no correction requirement that their
    contract covers.
* **Still to come:** the extension's replay, its families, and their own run, `natural-pr-v2` (protocol §20).

### Construction pilot (`pilot-v0.3.3`), a development study since protocol v0.7

Run `results/runs/pilot-v0.3.3`:
* 4 tasks × 6 conditions × 10 candidates = 240 graded pairs;
* harness 0.3.3, one code revision;
* no infrastructure outcomes;
* it agrees with the earlier runs `pilot-v0.3.2` (harness 0.3.2), `pilot-v0.3.1` (harness 0.3.1) and `pilot-v0.3`
  (harness 0.3.0) on all 240 pairs (D45), and its re-grade under harness 0.3.5 with three repeats,
  `pilot-v0.3.5-regrade`, gives the same outcome on all 240 (D54).

Of the 32 held-out candidates, 17 are labeled invalid, 10 valid and 5 ambiguous (excluded). The report is
`results/runs/pilot-v0.3.3/report.html`; the analysis is `results/runs/pilot-v0.3.3/analysis.md`.

| Condition | False acceptance | False rejection |
| --- | --- | --- |
| C1 initial-only, plain | 6/17 | 2/10 |
| C2 initial-only, audited | 5/17 | 2/10 |
| C3 correction-aware, plain | 0/17 | 0/10 |
| C4 correction-aware, audited | 0/17 | 0/10 |
| B2 full-session LLM | 1/17 | 0/10 |
| B1 repository tests (reference state) | 5/17 | 4/10 |

How to read this:

* **In this pilot, initial-only verifiers rewarded what the correction ruled out.**
  * Every invalid candidate they accept violates a correction-introduced requirement. That is largely by
    construction: 16 of the 17 invalid candidates violate one.
  * They accept both pre-correction states that are labeled invalid.
  * In `humanize`, where the correction retracted the initial request, they reject both valid alternatives and the
    reference solution.
* **The size of the gap depends on the session and on the contract proposer.**
  * In `tinydb` the proposer inferred the correction's requirements from the first request alone.
  * In `tinydb`, and by the rule's labels in `inflection` (the independent check disputes it there), the agent's own
    pre-correction state already satisfied the correction.
* **The audit changed one outcome.** Four of the eight audited verifiers needed no revision and are identical to their
  plain counterparts. On the 32 held-out outcomes of the other four, the audit changed one. It cannot repair a
  verifier whose contract is wrong.
* **Repository tests fail in both directions.** They miss the correction's invariants and over-specify the reference
  implementation. B1 includes 6–12 tests per task that the session agent added, and all four of its false rejections
  come from those tests. Restricted to the base commit's own tests (exploratory), B1 accepts 13/17 and rejects 0/10;
  both numbers largely follow from the label rule, whose valid label requires passing those tests.
* **Selection effect.** The ambiguous near misses are the hard cases. The exploratory views give these
  false-acceptance counts for the correction-aware verifiers:
  * 3 of 22 invalid candidates when constructed candidates are labeled by construction intent;
  * 6 of 25 under the independent construction checks' labels.
* **Duplicates.** Three held-out candidates duplicate a development attack used in their family's C4 audit: two
  `more-itertools` candidates have the same graded patch, and one `humanize` near miss differs by one docstring line
  (decision log D37, D40). Without them (exploratory), C1 accepts 4/14 and C3/C4 0/14.
* **Uncertainty.**
  * Cluster-bootstrap intervals over four families are wide. They are degenerate (zero width, marked) wherever every
    family has the same rate or difference, as for C3 and C4.
  * Exact binomial intervals are printed next to them; for 0/17 the upper bound is 0.20.
  * Eight candidates are in the human-review queue, five of them because the rule marked them ambiguous.

  **These are descriptive pilot numbers, not evidence of an effect.**

## How the measurement works

* **A measurement design.** Every verifier condition scores the *same* held-out candidate patches. In the construction
  pilot, each task's pool holds:
  * the agent's naturally observed **pre-correction state**;
  * constructed near misses;
  * independent valid alternatives.

  The pre-correction state is captured during the session. It existed before the verifiers, and its edits appear,
  abbreviated, in the session text that B2's generator and the full-session contract proposer read. The alternatives
  and near misses are generated only after the task's verifiers are frozen (CS-04's B1 was re-selected afterwards,
  decision log D31). The fresh-agent stratum adds attempts by agents given only the first request, or the first
  request and its correction: no reference, transcript, verifier, candidate or label (protocol §15.4). Their context
  also held harness material: an environment block naming the study repository and the build session's scratch
  directory, and task-list reminders with the titles (in CS-03 and CS-04 also the descriptions) of the build session's
  task-list items, in every attempt of CS-01 to CS-03 and in 16 of CS-04's 20 (protocol §18.2 as corrected in D62;
  paper §2.1, App. B). The conditions form a 2×2 grid:

  | | plain generated tests | + predefined audit (audit:v1) |
  | --- | --- | --- |
  | initial-request-only contract | C1 `initial_plain` | C2 `initial_audited` |
  | correction-aware contract | C3 `full_plain` | C4 `full_audited` |

  There are two baselines: B1 (repository tests at the reference state) and B2 (an LLM given the whole session,
  without contract machinery). Every generator gets the base repository and the reference diff, so the C1–C3 contrast
  isolates what the contract asks the generator to test, not what information reached it. The initial-only arm
  measures information lost during dataset construction, not agent capability.
* **Evidence-linked contracts.**
  * Each requirement carries a status (explicit, inferred, superseded or unresolved) and the turn that introduced it;
    explicit requirements carry exact quotes from the session.
  * Superseded requirements are never scored.
  * **Acceptance gate** (`src/tracecontract/contract.py`; its rules stand, D51, D84). A task passes
    only if its provenance record is `eligible`, its reconstruction record passed and was made from the current files,
    and every contract it lists is valid, has no unresolved requirement and has each scored inferred requirement (in
    the reference contract, each scored requirement) accepted by human review. Each human reviewer's latest decision
    counts: reviewers who disagree block a requirement until an adjudicated review is added, and `edit` or
    `needs_discussion` blocks it until a re-review accepts it. `tracecontract accept-task` sets the status to
    `accepted` only if the gate passes; `evaluate` runs the gate again, always refuses a rejected task or source, and
    evaluates a task that has not been accepted only with `--pilot`, which the run manifest records.
  * **No task can pass today.** `tracecontract accept-task tasks/<id> --dry-run` lists three kinds of reason for each
    of the four tasks: the provenance record is `pending_review`, and no command sets it to `eligible`; no requirement
    of the reference contract has a human review; and the initial-only and full-session contracts hold unresolved
    requirements and unreviewed inferred ones, which the blinded review packet does not show.
* **Process-separated grading** for C1–C4 and B2: harness `tc-harness/0.3.3` for the pilot, `tc-harness/0.3.5` for new
  runs.
  * Hidden tests run in a trusted grader.
  * Candidate code runs only as an unprivileged UID allocated to that container. It cannot read the tests or write
    the results.
  * Per-call results are authenticated, and the host recomputes outcomes, so a missing or stale result never becomes
    a reward.
  * **In-call limit:** within one call, code that the snippet runs, directly or through candidate modules it imports,
    still controls what that call reports. It can, for example, detect that it is being graded. Every test of these
    verifiers therefore asserts on a returned value, not only on success; the test lint flags any test whose only
    assertions are on success (decision log D3, D36, D40).
  * Adversarial Docker probes cover the boundary (`tests/test_sandbox_isolation.py`). They include regression probes
    for the defects found during the pilot and its reviews: two in resource isolation (decision log D29–D31) and two
    start-up paths for forged results, a module shadowing the standard library (D36) and an `encodings` package loaded
    while the interpreter starts (D40).
  * A later verification by model agents found a further path for forged results in 0.3.2: a candidate `ast.py` could
    load while the wrapper formatted a snippet's exception. Harness 0.3.3 closes it and adds a regression probe for it.
    No candidate patch in the pool ships an `ast` or `unicodedata` module (D44).
  * **Harness 0.3.5** (protocol v0.8 §16.1; D52) differs from 0.3.3 in one respect: a failure while formatting or
    encoding a value or an exception for a result message never turns a successful call into a failed one and never
    leaves a call without a result. What JSON cannot encode is converted by trusted code that calls no candidate
    method, or replaced by a placeholder naming the type. Candidate code that runs while the result is formatted (a
    `__repr__` or `__str__`) can still end or stall the call: the in-call limit, unchanged. 0.3.4 was never used for a
    run (D51).
  * **Exception:** the repository-test baseline B1 runs pytest with candidate code in the reporting process. An
    adversarial candidate can forge its report (see Limitations).
* **Controlled-session protocol (CS-v1):** scenarios hashed and logged locally before each run (not a formal
  preregistration), state capture between turns, transcript sanitisation and contamination audits.
* **Reconstruction check** (`tracecontract reconstruction-check`, v2; D47, D52): each base is tested against its own
  session from recorded material only. Every changed file needs a passed first-edit or base-read item, so a file whose
  base content the session's record does not attest makes the result incomplete. All four bases pass, with every
  changed file attested (`tasks/*/reconstruction_check.json`). The leakage check recorded in each `snapshot.json` was
  vacuous as called (D47); new builds record none.
* **Labels, checks and review.**
  * Label proposals come from a pre-specified rule (D19): independent reference checks, plus the regression norm, plus
    construction intent. Disagreement gives `ambiguous`.
  * An independent model check of every held-out candidate of the pilot (`tasks/*/labels/construction_checks.json`)
    is advisory only. For the fresh attempts, an independent labeler (protocol §15.5, D55) gives the second labeling.
  * A human-review queue that shows no verifier outcomes is in `tasks/*/labels/review_queue.json`. Reviewers open it
    only after their labels are merged.
  * Human labels are to be made from a blinded review packet (`tracecontract review-packet`): the session's user turns,
    the reference contract, and each held-out change under a random id, shuffled, with no proposal or outcome;
    identical changes share one id. The packet hides the origin field but not the origin, which the content can
    reveal: near misses resemble each other and the reference, and the user's corrections describe the agent's first
    attempt. Each reviewer therefore records an origin guess per candidate, and the merge reports how often the guesses
    on the tasks' own candidates are right. The key stays with a coordinator, and `tracecontract merge-reviews` needs
    two complete reviews per task (`docs/annotation_guide.md`, decision log D43, D44). It writes the reviews into the
    candidate files and the reference contract, which D47 freezes; it may, and the decision-log entry that records a
    merge gives the new hashes (D84).
    The packet takes the candidates that `task.json` lists and, with `--strata fresh-v1`, the fresh attempts that the
    analysis queues for review, which are stratum candidates. Their labels go to their files in the stratum, whose
    hashes `fresh-v1`'s `analysis.json` records among its inputs; since no guess option names a fresh attempt's
    origin, the guesses on them are counted by configuration and instruction variant (annotation guide, section 2;
    D82).
* **Harbor export** (pinned Harbor 0.25.0, separate verifier, only approved artifacts; exporter
  `tc-harbor-export/0.3.0`). Harbor makes the separate verifier's reward directory world-writable before the test
  runs; under the exporter of `c5ede4c`, two probes whose candidate code writes its own reward file (on a grader
  timeout and on a collection error) received reward 1.0. Since 0.2.0 the grade script locks the directory before
  candidate code runs and removes every reward file it did not write. 0.3.0 also refuses every task that the
  acceptance gate refuses (a rejected task or source, or a failed reconstruction check), and its verifier image has no
  setuid or setgid file. Validated with Harbor 0.25.0 under harness 0.3.5: oracle 1.0, a wrong candidate 0.0, no-op 0.0
  and no reward on either probe, while the `c5ede4c` exporter still gives 1.0 on both
  (`results/harbor_validation/tc-harbor-export-0.3.0/`). It exports only the reference solution unless candidates are
  named.

Related work: [docs/research_brief.md](docs/research_brief.md), adversarially verified by model agents (not yet
reviewed by a human), and `paper/sections/related.tex`. Each component of the design has partial precedents, notably
SessionFarmer, SWE-Together and Trace2Eval. What the paper adds is narrow (paper §6, Positioning): initial-only and
correction-aware verifiers from the same frozen procedure, scored on attempts by agents that did or did not see the
correction, with their own violations as negatives; and natural case studies. The claim that decision log D34 records
is a conjunction that also needs a held-out pool anchored on the sessions' own pre-correction states (the construction
pilot's) and independent human labels, which do not exist yet; the claim is the paper's present statement of
contribution (D84; `docs/ownership_and_defense.md`, §4 item 9), and paper §7 describes the design to aim for once
human labels exist.
The pool's departures from blindness are listed under Limitations.

## Reproduce in full

Requirements:
* Linux, Python 3.13 (tested; the package needs ≥ 3.12, and if 3.13 is missing `uv venv --python 3.13` downloads a
  managed build, which needs network access), [uv](https://docs.astral.sh/uv/), `git`, and Docker with the daemon
  running;
* a clone with the repository's full history: `paper/make_tables.py --design` reads the protocol's early versions
  from their commits;
* network access from the host: github.com to rebuild the base snapshots (`tracecontract snapshot` fetches each pinned
  commit with git), Docker Hub for the digest-pinned `python` base image, and PyPI for the package install and the
  wheelhouses. Grading itself needs no network;
* for the paper and its figures: a TeX distribution with `latexmk`, `biber`, and `pdflatex` with TikZ and the
  `standalone` class;
* for the Harbor check only: a Harbor 0.25.0 CLI in a separate environment.

The `dev` extra installs `pip` into the venv; image builds call `<venv python> -m pip download`.

### Install and test

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -c constraints.txt -e ".[dev,data]"
```

```bash
.venv/bin/python -m pytest -q -m "not docker"   # offline tests: fixtures, plus read-only checks of the recorded tasks, transcripts and runs
```

```bash
.venv/bin/python -m pytest -q -m docker          # grading-isolation probes and the fresh-agent wrappers (needs Docker)
```

`.venv/bin/python -m pytest --collect-only -q` lists the tests, all of them only with a reachable Docker daemon: without
one, `tests/test_sandbox_isolation.py` is skipped whole at collection, and 19 fewer are listed. It lists 1,465: 1,445
offline and 20 Docker. In a fresh clone 23 offline tests skip: 14 until the base snapshots are built (next block),
and 9 that need the git-ignored natural data (`data/natural/`), which is not published. On 2026-11-25, in a clone with
the snapshots built, 1,436 offline tests passed and 9 skipped; in the build checkout, which holds the natural data,
all 1,445 offline tests and the 20 Docker tests passed (D84).

### Tasks, grading and runs

```bash
for t in CS-01 CS-02 CS-03 CS-04; do .venv/bin/tracecontract snapshot tasks/$t; done   # rebuild every base snapshot from its pinned commit
```

```bash
.venv/bin/tracecontract reconstruction-check tasks/CS-01   # the base against the session's own record: exit 0 passed, 1 a check failed, 2 incomplete (for example, no snapshot built); --write records it
```

```bash
.venv/bin/tracecontract validate-task tasks/CS-01
```

```bash
.venv/bin/tracecontract accept-task tasks/CS-01 --dry-run   # the acceptance gate: what blocks the task (exit 1); changes nothing
```

```bash
.venv/bin/tracecontract grade tasks/CS-01 full_audited CS-01-pre-correction
```

```bash
.venv/bin/python scripts/preflight_final_run.py tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04 --run-id my-run --conditions initial_plain initial_audited full_plain full_audited llm_freeform repo_tests --repeats 3 --pilot
```

```bash
.venv/bin/tracecontract evaluate tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04 --run-id my-run --conditions initial_plain initial_audited full_plain full_audited llm_freeform repo_tests --repeats 3 --pilot
```

`--pilot` is required because no task has passed the acceptance gate; without it, `evaluate` refuses the four tasks
and writes nothing. A new run grades every pair three times under harness 0.3.5 or later; the pre-flight fails
otherwise (protocol §15.3, §16.1). The recorded re-grade of these 240 pairs with three repeats ran for about an hour
(07:21:53 to 08:18:38 UTC, `pilot-v0.3.5-regrade`, D54).

```bash
.venv/bin/tracecontract analyze results/runs/my-run --allow-proposed-labels   # --reporting-rules auto (the default): the v0.8 reporting rules for a run graded with harness 0.3.4 or later, the pilot's analysis otherwise
```

```bash
.venv/bin/tracecontract report results/runs/my-run --out results/runs/my-run/report.html
```

```bash
.venv/bin/python scripts/compare_runs.py results/runs/pilot-v0.3.3 results/runs/my-run
```

### Re-analyse the recorded runs

`fresh-v1` was analysed with its sensitivity view, which excludes every attempt that the automated audit flagged
(protocol §18.1). To regenerate its analysis and report from the recorded results, in a copy of the run:

```bash
cp -r results/runs/fresh-v1 /tmp/fresh-v1-copy
.venv/bin/tracecontract analyze /tmp/fresh-v1-copy --allow-proposed-labels $(for t in CS-01 CS-02 CS-03 CS-04; do echo --sensitivity-exclusions data/fresh/fresh-v1/audit_$t.json; done)
.venv/bin/tracecontract report /tmp/fresh-v1-copy --out /tmp/fresh-v1-copy/report.html
cmp /tmp/fresh-v1-copy/analysis.md results/runs/fresh-v1/analysis.md && cmp /tmp/fresh-v1-copy/report.html results/runs/fresh-v1/report.html
```

`analysis.md` and `report.html` come out byte for byte. `analysis.json` and `analysis_sensitivity.json` differ only
in the git revision and code hashes they record, and `analysis_sensitivity.md` only in the hash of `analysis.json` it
names. Without the four `--sensitivity-exclusions` files, the report states that its sensitivity view was not computed
with the current `analysis.json`.

```bash
.venv/bin/python scripts/verify_frozen_inputs.py   # pilot-v0.3.3's frozen files and inputs unchanged; its analysis and report regenerate byte for byte (needs the four snapshots of the snapshot loop and the full git history)
```

```bash
.venv/bin/python scripts/exploratory_reanalysis.py   # post hoc, exploratory re-analysis of pilot-v0.3.3 and planning simulation (D49)
```

The frozen-input check compares against the commit `c5ede4c` and regenerates the analysis and report in a temporary
copy of the run directory; it is run at the end of every phase. It exempts two things only: the git revision that
`analysis.json` records, and analysis code that changed since the run, as long as the analysis and report regenerate
byte for byte. Nothing else is exempt: the rule-based triage proposals of the four tasks are kept in the sidecars
`tasks/<id>/triage.json`, and the provenance records are back to their bytes at `c5ede4c` (D52). The exploratory
re-analysis reads the frozen run and the task records without changing them, and writes
`results/analyses/pilot-v0.3.3-exploratory/`, `paper/generated/exploratory/` and
`paper/evidence_ledger_exploratory.md`; every table it writes is marked post hoc and exploratory.

### The paper's numbers, tables and figures

```bash
.venv/bin/python paper/make_tables.py results/runs/pilot-v0.3.3 --compare results/runs/pilot-v0.3.2 results/runs/pilot-v0.3.1 results/runs/pilot-v0.3 results/runs/pilot-v0.2 results/runs/pilot-v0.2-h2
```

```bash
.venv/bin/python paper/make_tables.py --fresh results/runs/fresh-v1 --regrade results/runs/pilot-v0.3.5-regrade --natural   # the lead result, the re-grade and the natural screening
.venv/bin/python paper/make_tables.py --pilot-numbers results/runs/pilot-v0.3.3                                         # the construction pilot's numbers
.venv/bin/python paper/make_tables.py --design                                                                          # design constants and the protocol amendments (needs the full history)
.venv/bin/python paper/make_tables.py --natural-run results/runs/natural-pr-v1                                          # the natural case studies
.venv/bin/python paper/make_figures.py results/runs/fresh-v1                                                            # Figures 1 and 2 (needs pdflatex with TikZ)
.venv/bin/python paper/check_numbers.py                                                                                 # every number in the text is a generated macro
.venv/bin/python scripts/check_abstract.py                                                                              # the abstract's length without TeX markup (at most 1,900 characters)
```

```bash
cd paper && latexmk -pdf main.tex
```

The first command writes the construction pilot's tables, frozen at `c5ede4c`, to `paper/generated/*.tex` and
`paper/evidence_ledger.md`. Every other mode writes its own directory under `paper/generated/` and its own ledger
(`paper/evidence_ledger_*.md`) and leaves the rest untouched; each regenerates the committed files byte for byte, so
`git status` stays empty. [`paper/README.md`](paper/README.md) documents every mode and the rules for numbers.

### Inspect a candidate, check the Harbor export, build attempts

To write one candidate's final file state to a directory without running any code (reviewers label from the blinded
packet and use this only after their labels are merged):

```bash
.venv/bin/tracecontract materialize tasks/CS-01 CS-01-pre-correction --out /tmp/review-CS-01-pre
```

To re-check the Harbor export on the synthetic fixture task, with Harbor 0.25.0 in its own environment:

```bash
uv venv /tmp/harbor-venv && uv pip install --python /tmp/harbor-venv/bin/python harbor==0.25.0
CONTROL_REV=c5ede4c HARBOR=/tmp/harbor-venv/bin/harbor scripts/harbor_validate.sh
```

It runs the oracle, wrong-candidate, no-op and two reward-planting probe trials, and, with `CONTROL_REV`, both probes
again under the exporter of `c5ede4c`. It rewrites the recorded outputs in
`results/harbor_validation/tc-harbor-export-0.3.0/`: `summary.json` comes out byte for byte, and the trial files differ
only in their ids and timestamps. Without `CONTROL_REV` it drops the recorded control trials.

The tools that built and audited the 80 attempts of `fresh-v1` (protocol §15.4, §16.2; D56, D57): a workspace, the
registration of an attempt, and its audit.

```bash
.venv/bin/python scripts/make_agent_workspace.py tasks/CS-01 --role fresh --variant u1 --image <the task's sandbox image> --root <directory outside the repository> --name CS-01-fresh-A-u1-1   # instruction u1 with the recorded path substitution
.venv/bin/tracecontract add-stratum-candidate tasks/CS-01 fresh-v1 CS-01-fresh-A-u1-1 --state-dir <workspace>/repo --origin fresh_attempt --attempt-record <attempt.json>   # task.json is never changed
.venv/bin/python scripts/strict_reaudit.py --fresh <attempts.json> --transcripts <transcript directory> --report <report.json>   # everything outside the attempt's workspace is forbidden
```

### What regenerates, and what is published

Model-generated artifacts (sessions, contracts, tests, candidates, label proposals, checks and mappings) are recorded
in the repository. The prompts that produced them are in `experiments/prompts/`, with owner messages and session paths
redacted. The controlled sessions' own transcripts are committed in sanitised form (`data/controlled/transcripts/`);
the transcripts of the other agents, the generators and the fresh attempts among them, are not published. Regenerating
these artifacts is not bit-reproducible. From the recorded results, the analyses, tables, figures, evidence ledgers,
reports and run comparisons regenerate byte for byte, except what records the current git revision and the hashes of
the analysis code: `analysis.json` (with a sensitivity view's `analysis_sensitivity.json`, and the hash of
`analysis.json` that its `analysis_sensitivity.md` names). The analysis code has changed since the runs without
changing any output (D46 records the first such change, to `schemas.py`). `scripts/verify_frozen_inputs.py` checks
the analysis and report of `pilot-v0.3.3`, and the frozen inputs, at the end of every phase. Re-grading reproduces
outcomes, not bytes: results carry timestamps and durations, and tests have time limits. The natural run publishes
only identifiers, hashes, counts and outcomes (`results/runs/natural-pr-v1`); its tasks, with their pseudonymised
threads, stay in the git-ignored `data/natural/`, and its raw results are git-ignored too, so it can be neither
re-graded nor re-analysed from the release. Its tables regenerate from the published `analysis.json`. The natural
arm's screening and download records (`data/manifests/`) also hold the commented files' paths, 120 checked
model-written paraphrases of qualifying review comments, and the URLs of the 63 repositories of stage S9 with the
pull-request refs fetched there (owners that act in AIDev masked as `{owner}`); the URLs stay, as public provenance
(D84; `docs/data_card.md`, Personal information). Every number in the
paper's generated tables and macros has an entry in an evidence ledger (`paper/evidence_ledger*.md`) with its source
file.

Before each push, `.venv/bin/python -I scripts/scan_tracked_files.py --private-markers <file kept outside the
repository> --aidev-logins <AIDev directory> --natural-texts data/natural/tasks` is run as a manual step, not as a git
hook (`-I`, since the AIDev parquet files are third-party data). It checks the working tree and every file version in
the commits the push would send for credentials, session-local paths, e-mail addresses and the private markers
(decision log D44). With `--aidev-logins` it also checks for the 119 logins and names tied to the sampled AIDev pull
requests, loaded in memory from the AIDev files, and for @handles in files under `tasks/` and `data/` (D48, D52).
With `--natural-texts` (since D69) it also checks for the natural tasks' thread texts, their repositories' names and
owners, and the upstream code lines of their candidates, verifiers and base snapshots, and for @handles under
`results/` and `experiments/` (protocol §17.4); `--screening-texts <file.jsonl>` (the S9 and S9x sample texts, kept
outside the repository) adds the texts of every sampled comment.
Earlier commits, already pushed, still hold material that has since been removed; STATUS.md lists it.

## Layout

```
src/tracecontract/   schemas, ingest/, contract, snapshot, reconstruction, patches, sandbox/, verifier, audit,
                     evaluate, strata, metrics, stats, analysis, report, review, duplicates, triage, shadowing,
                     harbor_export, controlled, natural_pr, natural_env, natural_privacy, roots, tasks, store, cli
tasks/<id>/          task manifests, provenance, triage proposals, contracts (+ mappings), candidates, strata/
                     (the fresh attempts), verifiers, labels, reconstruction check
data/                manifests (incl. natural-data screening records), sanitised controlled transcripts, scenarios,
                     reference proposals, fresh-attempt records (data/fresh/), labeler audits
experiments/         protocol.md (amendments up to v0.12, §20), precision_plan_v1.0-draft.md (not adopted),
                     downstream_plan_v0.1-draft.md (a draft, not run, not adopted), prompts/ (workflow scripts and
                     agent prompts), natural_workflow/ (the natural recipe's workflow)
configs/             the downstream plan's data-step configuration (configs/downstream/), applied post hoc to fresh-v1
results/runs/<id>/   manifest, raw results, analysis, comparisons, report (logs are local only); the natural run as
                     identifiers, hashes and outcomes
results/analyses/    post hoc, exploratory re-analyses of frozen runs
results/harbor_validation/  recorded Harbor validation outputs (fixture task)
scripts/             label proposals, construction checks, review queues, duplicates, preflight, run comparison,
                     publication scan, frozen-input check, exploratory re-analysis, natural-data screening and
                     publication, agent workspaces, abstract check, training selection
docs/                research brief, decision log, data card, annotation guide, internal review, status docs
THIRD_PARTY_LICENSES/ licence notices of the redistributed upstream code
paper/               LaTeX manuscript, bibliography checked by model agents, table and figure generators, number
                     checker, evidence ledgers
LICENSE              MIT licence of the code
LICENSE-DATA         CC BY 4.0 licence of the study's data, documentation and text
CITATION.cff         citation metadata
```

## Licence and citation

The code is under the MIT licence ([`LICENSE`](LICENSE)). The data, documentation and manuscript text that the study
created are under CC BY 4.0 ([`LICENSE-DATA`](LICENSE-DATA)). Third-party material keeps its own licence: the
upstream code and the upstream lines in candidate patches and transcripts, the records extracted from AIDev v5
([`THIRD_PARTY_LICENSES/`](THIRD_PARTY_LICENSES/README.md)), and quotations from other works in the documents. To cite this work, use [`CITATION.cff`](CITATION.cff).

Author: Raj Kashikar, Cornell University (rsk239@cornell.edu).
