# Decision log

Significant scientific and engineering decisions, in order. Each entry states the
decision, the evidence, and what would change it. Times are UTC.

## 2026-11-13

### D1. Working name, question, and scope kept for now
TraceContract; research question and hypothesis as in the project brief. The
literature review (docs/research_brief.md) may narrow the claim; see later entries.

### D2. Execution environment and sandboxing
* Cloud container: 4 CPUs, 15 GiB RAM, ~31 GB free disk, **no GPU**. Docker 29.9.2 was
  started inside the container (`dockerd`), image pulls work, `--network none` works.
* LaTeX (TeX Live 2023, latexmk, biber) installed from Ubuntu packages.
* No model-API key is configured for paid use; additional external API/cloud/GPU
  spending is **zero** (default in the brief). Model-generated artifacts are produced
  through this Claude Code session's own subagents and recorded with prompts and
  outputs.
* Untrusted repository code is never executed on the host. Running a third-party
  test suite directly on the host was blocked by the session's safety classifier,
  which matches the brief's rule. All repository code (including code run by the
  controlled-session agent) runs in Docker with `--network none`, all capabilities
  dropped, `no-new-privileges`, read-only mounts and resource limits.
* Docker images are built **offline** (`docker build --network none`) from a
  host-downloaded, fully pinned wheelhouse (wheels only, `--no-deps`, transitive
  closure pinned). Reason: the egress proxy re-terminates TLS and the proxy CA must
  not be baked into task images; the wheelhouse is also more reproducible.

### D3. Grading isolation design (process separation)
Hidden tests run in a trusted grader process (root, inside the container) and reach
candidate code only through child processes running as an unprivileged UID
(`tc_sandbox.run_python` / `run_cmd`). The sandbox UID cannot read `/grader`
(hidden tests) or write `/results`. Each child result carries an HMAC over a
per-call key sent through an inherited pipe; generic output tampering is detected.
The host recomputes the outcome from `results.json` and a per-run nonce; missing,
stale, or unparseable results are `verifier_error`, never `pass`.
Residual risk (documented): code inside a child controls that child's reported
values; a targeted attack on the wrapper could forge a single call's result, so
tests must assert on concrete returned values. Repository-native test suites
(baseline B1) necessarily import candidate code and are marked `in_process`.

### D4. Data populations and source plan
* **Natural**: SWE-chat (`SALT-NLP/SWE-chat`, ODC-BY, gated auto-approval with
  username/email sharing). The repository owner approved use and a read-only HF
  token was saved to the session environment, but the dataset terms have **not yet
  been accepted** and the token check (`/api/whoami-v2`) currently returns 401.
  The natural-data path is therefore blocked; ingestion code is written and tested
  on fixtures only.
* **Controlled**: real agent runs (a Claude Code general-purpose subagent) on
  pinned, permissively licensed public repositories, with user turns written by the
  study before the run (scripted users). These are labelled `controlled` and are
  never described as natural or production traffic. Scripted user feedback is
  synthetic.
* **Fixture**: hand-written synthetic unit-test fixtures.

### D5. Controlled-session protocol (CS-v1)
* Each scenario (initial request U1, correction U2, a fixed neutral reply for
  clarification questions, and the study's *intended requirements*) is written and
  hashed **before** the agent run. The scenario text is kept outside the repository
  until the session ends so the agent cannot read it; only the hash is logged.
* Intended requirements written before the run are the independent ground truth for
  the reference contract (subject to human review); the proposed method never sees
  them.
* After the run, the transcript is audited for file access outside the workspace;
  contaminated sessions are rejected and recorded in the rejection ledger.
* Workspace: `git archive` export of the pinned commit (no history), a fresh git repo
  with a single base commit, and sandbox wrapper scripts for running tests/Python.

Registrations:

| Scenario | Registered (UTC) | sha256 | Note |
| --- | --- | --- | --- |
| CS-01 | 2026-11-13T01:41:56Z | ac516594161a52977171f8c6a98a75eb4b131d825385dfc9b43d24e60ce05837 | first registration |
| CS-01 | 2026-11-13T01:43:43Z | 8bc295e09192a223c640b8d55fb799661a865bee773de5dac8abfb2249ed42ad | supersedes the above before the run: U1 tooling sentence now points at sandbox wrapper scripts instead of a virtualenv (host execution blocked) |
| CS-02 | 2026-11-13T01:51:38Z | f8a0dfaddb2f5ef0a8b1a447174cb76037f9658dbf65c9c8a8de3c50f8ceeb88 | TinyDB JSONStorage atomic writes |
| CS-03 | 2026-11-13T01:51:38Z | 656b29202874bcde581cc0b5d47e49ac3108564fcf0d9ebcef8aaea2679fea0a | inflection titleize acronyms |
| CS-04 | 2026-11-13T01:51:38Z | fa160de3c75774a2f4dbbc7f70b7bf1a92674a6e106e3253f46a3720e471f2d6 | more-itertools consecutive_groups step |

State captures: CS-01 `after_U1` captured 2026-11-13T01:52:24Z (manifest
aa4a68abafc9f49a317689fbe6442d9ce040a39a27f65fc9647889a6bb8d3424) before U2 was sent.

### D6. CS-01 initial-state approximation
humanize generates `src/humanize/_version.py` at build time (hatch-vcs). The build
backend is not run on the host; a fixed `_version.py` is added to the workspace and
recorded as a snapshot approximation (`fidelity = approximate`). The file is
gitignored upstream, so it does not appear in candidate diffs.

### D7. Isolation fix found by the probe suite (`--init`)
The probe `test_daemon_leftovers_are_reaped` found 64 sandbox-UID processes alive
after a fork-bomb probe. The reaper's SIGKILLs worked, but orphaned children were
re-parented to PID 1 (the grader), which does not reap them, so they remained as
zombies counted against the sandbox user's process limit. Grading containers now
run with `docker run --init`; the probe passes. This only affected later calls of
the same (adversarial) candidate's grading run, never another candidate.

### D8. Controlled-session environment specifics
* CS-02 (TinyDB): upstream `pytest.ini` adds coverage options; the sandbox wrapper
  passes `-o addopts=` so pytest-cov is not needed (coverage would try to write to
  the read-only mount).
* Baselines inside the sandbox at the pinned commits: CS-01 741 passed
  (filesize, number, lists, time, doctests in src; i18n tests need compiled .mo
  files and benchmark tests need pytest-codspeed, both excluded); CS-02 227 passed,
  1 skipped; CS-03 467 passed; CS-04 771 passed (plus subtests).

### D9. Transcript sanitisation before publication
Subagent transcripts carry harness internals (request ids, classifier context,
attachments, internal session/agent ids, working directories). Before a transcript
is committed it is minimised by `ingest.claude_code.sanitize_transcript`: only
user/assistant messages (text, tool calls, tool results), timestamps, entry ids,
model name and token usage are kept, and entries are relabelled with a study
session id (e.g. `CS-01-session`). Hashes of the original and the sanitised file
are recorded; all downstream processing uses the sanitised file so that
provenance is reproducible from the repository.

### D10. Delivery of scripted corrections (limitation)
Scripted turn U2 is delivered to the running agent through the subagent messaging
channel, which wraps it as "The coordinator sent a message while you were working:
... Address this before completing your current task." The wrapper is harness
framing, not user text; the parser classifies any user-role entry containing a
registered scripted turn as a scripted user prompt (`scripted_turns`), and evidence
spans point into the delivered text. The framing is a real deviation from a natural
session (the agent may perceive a coordinator rather than an end user) and is
reported as a limitation of the controlled population.

### D11. Reference contracts for controlled tasks
Reference contracts are operationalised from the pre-registered intended
requirements by adding exact evidence quotes from the registered turns
(`data/controlled/reference/<id>.json`, validated by the same machinery as model
proposals). For CS-01 this operationalisation was written after the U1 output was
seen; the statements follow the registration, with one wording change for internal
consistency: "keep meaningful decimals" is phrased so that it holds both with and
without the opt-in flag. CS-02..CS-04 were operationalised before their sessions
produced output. Each reference requirement carries a model review only; the task
acceptance gate keeps every task `pending_review` until a human reviews it.

### D12. Ground truth sealed during generation
While verifiers, attacks and alternatives are generated, the reference contract,
scenario file and reference proposals of the task are moved out of the repository
(to the session scratchpad), so generation agents cannot read them. They are
restored after verifiers are frozen. Generation-agent transcripts are additionally
audited for file access outside their permitted inputs.

### D13. Baseline B1 (repository tests) definition
B1 = the repository's test files as they exist in the reference (final) state,
overlaid on the candidate (candidate edits to protected test paths are discarded),
restricted to the tests that pass on the reference itself (PASS-on-reference
selection). Doctests embedded in candidate source files are excluded (they are
candidate-authored). B1 runs `in_process` (the candidate is imported by pytest).
CS-01: 737 checks; reference passes, pre-correction state fails 49, no-op fails 11.

### D14. Generation conditions and leakage controls
* Plain conditions (C1 initial_plain, C3 full_plain, B2 llm_freeform): single-pass
  test generation. Generators may read the base repository and the reference
  diff and may query BASE behaviour in the sandbox, but may not execute their tests
  against any candidate.
* Audited conditions (C2, C4) start from the corresponding plain tests and apply
  audit:v1 with development candidates only (reference, no-op, 4 development
  attacks and 1 development valid alternative per contract variant), with at most
  3 revision rounds.
* All conditions use the same generator (Claude, via Claude Code workflow
  subagents) and the same prompt template; only the contract input differs.
* Evaluation candidates (independent valid alternatives, constructed near misses)
  are generated only after all verifiers of the task are frozen, in workspaces that
  contain no verifier files.

### D15. Protocol v0.1 timestamped before any evaluation run
`experiments/protocol.md` v0.1 (pilot, exploratory) written and hashed at 2026-11-13T02:08:30Z,
sha256 `a7cd8be82373fe22a619ac4e6759172499fd340160e3cc89403db78ba175d379`. No evaluation run had been executed at that time (only the
B1 construction run on the CS-01 reference, the no-op and the pre-correction
candidate used as smoke checks of the repo-tests mode). Not a formal preregistration.

### D16. Exported contracts carry the introducing user turn
`export-gen-workspace` includes `introduced_in_user_turn` for each scored
requirement (part of the structured contract: time introduced). The change was
made before any generator of CS-01 or CS-04 had exported a contract, so all
conditions of all tasks use the same format. Initial-only contracts contain only
turn-1 requirements by construction; B2 receives no contract.

### D17. Contract-proposal tooling fix (`id` alias) and CS-01 generation restart
The `contract:v1` prompt asks for "an id (R1, R2, ...)" without naming the JSON
key. The CS-01 full-session proposer wrote `id` instead of `req_id`; the tooling
defaulted every id to `?`, and `make-contract` crashed on duplicate ids (three
attempts by the agent). Fix: `requirements_from_proposals` accepts `id` /
`requirement_id` as aliases and rejects missing or duplicate ids as explicit
proposal rejections. The prompt was **not** changed, so all tasks use the same
prompt text. The CS-01 full-session contract was then built from the proposer's
own recorded `proposals.json` (unchanged) with the fixed tooling: 9 requirements,
0 rejected. The CS-01 generation workflow, which had started its test generators
against the missing contract, was stopped and resumed from its run id (contract
steps cached, generation steps re-run live). CS-04's proposer ran after the fix.

### D18. B1 on the natural pre-correction candidates
* CS-03: the pre-correction state passes all 466 B1 checks; the agent had already
  kept all-uppercase input unchanged in its first turn, so the correction mostly
  restated behaviour the agent had chosen. Whether this candidate is valid is
  decided by the labels, not by its origin.
* CS-04: the pre-correction state fails 1 of 616 B1 checks (the agent's own
  step=0 test written after the correction).

### D19. Automated-pilot label proposal rule (pre-specified before any evaluation run)
Evaluation-candidate labels for the automated pilot are proposed by
`scripts/propose_labels.py` from three sources: (1) an independent
`reference_check` verifier written from the reference contract by a separate agent
and validated only on the reference solution and the no-op; (2) the regression
norm, i.e. base-commit repository tests that pass on the reference but fail on the
candidate; (3) the construction intent recorded by the candidate's generator.
Agreement yields `valid`/`invalid`; any disagreement or missing decision yields
`ambiguous` (excluded from FA/FR, queued for human review). Natural candidates have
no construction label and are labelled from (1)+(2). Labels are appended with
`labeler_kind = model` and never override human labels. The reference-check
verifier is not one of the evaluated conditions. Known circularity: the
regression norm uses base tests that also appear in B1, which can favour B1 on
regression-only negatives; negatives are therefore reported by type.

### D20. Harbor export validated on a synthetic fixture
`harbor_export.export_task` was validated with Harbor 0.25.0 on a synthetic fixture
task (population `fixture`; not research evidence): `harbor lint` rc=0; `harbor
trial start -a oracle` with `CANDIDATE=reference` → reward {reward: 1.0, R1: 1.0};
with a wrong candidate → 0.0; `-a nop` → 0.0. In every run the candidate's edit to
a protected test file was discarded before grading (`tc_detail.json`). The runs used
the `local-validation` network variant (public network) because this host cannot
run Harbor's `no-network` mode; the fixture candidates were trusted code. (A first
no-op attempt failed with an environment error because the trial name produced an
invalid Docker tag; Harbor recorded it as an exception, not as a reward.)

### D21. E-mail redaction in published transcripts; local paths removed from notes
Sanitised controlled transcripts contained the public e-mail addresses of upstream
project authors (tool results showing repository metadata). Sanitisation now
redacts e-mail addresses in all message content (`[EMAIL REDACTED]`; CS-01: 2,
CS-03: 1, CS-04: 1). Line structure is unchanged, so event ids and evidence spans
are unaffected; provenance records carry the new transcript hashes and
`redaction_status = redacted_by_us`. Generation agents that rendered sessions before
this change saw the unredacted e-mails in tool results; this does not affect any
requirement. Absolute session-local paths in research notes were replaced with
`<scratchpad>` / `<session-dir>`.

### D22. Protocol v0.2 (before any evaluation run)
Amended at 2026-11-13T02:29:52Z after the verifier-fidelity literature review (Youden's J,
task-level accepted negatives, origin stratification, label rule D19, generator
diversity limitation). sha256 `b507dc232be96880cf08501fc5079fbc30918cf0713c0006b7bf44e52f7360ba`. No evaluation run had been executed.

### D23. CS-02 capture-race check; state captures visible to the agent (protocol note)
* For CS-02 the `after_U1` capture and the U2 delivery were issued in the same
  tool batch. The transcript shows U2 delivered at 02:18:44.086Z, the capture
  completed within the same second, and the agent's first tool call after U2 at
  02:24:23Z (first edit 02:24:32Z), so the captured state precedes any U2 change.
* The CS-02 agent noticed the `states/` capture folder inside its workspace root
  (`/home/user/cs_workspaces/CS-02/states`). It contains only the agent's own
  earlier work, not study material, so the session is not contaminated; but for any
  future controlled session, captures are stored outside the agent's workspace root.
* B1 (CS-02): 239 checks; pre-correction fails 3, no-op fails 5.

### D24. Workflow subagents refused deterministic steps; audits re-run by the trusted host
Several low-effort workflow subagents (audit runners, the freeze step, and one
attack generator) refused to run, reading the owner's message about not accepting
dataset terms as a request to pause. Some revision agents then rewrote C2 tests from
scratch based on the refusal text, so those C2 tests no longer derived from C1.
Remedy: the generation workflows for CS-04 were stopped; for every task the audited
verifiers are reset to exact copies of their plain tests (C2 := C1, C4 := C3) and
audit:v1 is executed directly by the host CLI (deterministic; no agent), with
revision agents (normal effort, accurate context about the owner's instructions)
used only when an audit reports findings. Freezing is also done by the host CLI.
Missing development attacks (CS-01 initial-only) are regenerated with the same
prompt template plus that context note.
* CS-04: C2 and C4 audits pass with zero revisions (C2 ≡ C1, C4 ≡ C3); all six
  verifiers frozen.
* CS-01: C4 audit passes with zero revisions (C4 ≡ C3); C2 pending regenerated attacks.

### D25. Contribution narrowed after the novelty search (scope decision)
Evidence (research notes `newest_closest.md`, `swechat.md`, `corrections.md`,
`verifier_fidelity.md`): SessionFarmer/CropChat (arXiv 2611.02440, v1 2026-11-02)
already reconstructs correction-aware executable tasks from SWE-chat with
event-cited requirements, compares first-message vs full-episode statements by
coverage, refines tests against mutants and reports FP/FN against LLM-assigned
patch labels; SWE-Together, PersonaCodeBench, AfterVibe and FeatureLoop cover
other parts; VerifierBench scores generated verifiers on held-out pools of valid
and invalid variants. Task reconstruction, correction-aware statements, mutant
refinement and held-out verifier scoring are therefore **not** claimed as new.
Remaining claim (to be stated in the paper and brief): a pre-specified,
verifier-level counterfactual measurement of correction-attributable false
acceptance and false rejection: verifiers produced by one frozen procedure from
initial-only vs correction-aware contracts, with and without a predefined audit,
plus repository tests and a full-session LLM baseline, all scored on one frozen,
held-out candidate pool whose anchor negatives are the agent's own pre-correction
states, with independent valid alternatives and near misses, against independent
human labels (and the discrepancy between model-proposed and human labels
reported). Until human labels and natural sessions exist, the repository supports
only an infrastructure-and-design contribution plus a controlled automated pilot.

### D26. Sealed material moved out of the scratchpad; contamination scan of all generation transcripts
Subagents are told the session scratchpad path, so sealed ground truth stored there
(D12) was reachable by any agent that listed the directory. All sealed material
(reference contracts, scenarios, reference proposals of unfrozen tasks) was moved
to a hidden, mode-0700 directory that no agent prompt names (`/home/user/.tc_sealed`).
A scan of all 78 agent transcripts available at that point (workflow and standalone
subagents) for reads of sealed/scenario/reference-contract locations found exactly
one access: the CS-04 requirement-mapping agent reading `contracts/reference.json`,
which is its task. Evaluation-side generators are additionally audited per agent
(`scripts/audit_eval_generators.py`); CS-04-eval-alt-1: 0 forbidden reads.

### D27. Audit outcomes that cannot be repaired faithfully; reference-check writers listing directories
* CS-01 C2 (`initial_audited`): audit:v1 reports `reference_not_passing` (the final
  solution keeps the default output, which the initial-only contract requires to
  change). The revision agent kept the tests faithful to the initial-only contract
  (adding only near-tie checks for an initial requirement) and reported that no
  contract-faithful suite can make the reference pass. Recorded as audit
  `passed = false` after 1 revision and frozen ("at most 3 revisions"; further
  rounds cannot change the outcome). Interpretation: the predefined audit
  *detects* the contract-reference inconsistency caused by the lost correction but
  does not *repair* the verifier when the reviser stays faithful to the contract.
  The reviser suggested using a contract-conforming development alternative as the
  positive control for initial-only contracts; audit:v1 is not changed mid-study,
  and the suggestion is recorded for a future protocol version.
* CS-03 audits: C2 and C4 each passed after one revision that closed a real gap
  (an attack slipping past). CS-04: both audits passed with zero revisions.
* The CS-03 and CS-04 reference-check writers each ran one `ls` on the task's
  `verifiers/` directory (names only; no other verifier's tests were read).
  Assessed as benign; recorded in `tasks/<id>/labels/generator_audit.json`.

### D28. Repository-test hangs are recorded as task failures in run pilot-v0.2 (known limitation)
In run `pilot-v0.2`, B1 (`repo_tests`) on CS-04-eval-alt-1 ran pytest at full CPU
for over 7 minutes (other candidates: ~20 s), i.e. one of the reference state's
repository tests appears to loop or run pathologically on this candidate. The
in-container pytest call has a 600 s limit; on expiry no JUnit report exists, and
the current aggregator records `task_failure` ("repository tests failed to
collect") rather than `timeout`. Both are non-pass outcomes, so the primary FA/FR
analysis is unaffected; the infrastructure breakdown is. The aggregator is not
changed during the run (so every task in the run uses one code revision); the
mapping of repo-test timeouts to `timeout` is scheduled for the next harness
version, and the affected results are identified from their diagnostics.

### D29. Harness 0.2.0: per-container sandbox UID; repo-test timeouts recorded as `timeout`
**Finding (2026-11-13).** Diagnosing D28 showed that the B1 stall on CS-04-eval-alt-1
was not caused by the candidate. Re-running that pair with the real grader gave two
failures, `TestSynchronized::test_concurrent_calls` and
`TestConcurrentTee::test_concurrent_consumers`, both `RuntimeError: can't start new
thread`. A second re-run aborted with a pytest INTERNALERROR (MemoryError). Outside
the grader, the same reference-state suite passes 777/777 in 37 s.

**Cause.** Every grading container ran candidate code as the same fixed UID (1001).
The sandbox sets `RLIMIT_NPROC` = 64, and the kernel counts that limit per UID across
the whole host, not per container. Any other process of UID 1001 therefore consumes
the grader's thread and process budget, including concurrent grading runs and the
interactive sandbox wrappers. Isolated probe: a container started 30/30 threads alone
but 2/30 while another container held 60 threads as UID 1001. Outcomes could thus
depend on unrelated concurrent load. A candidate could also starve concurrently
graded candidates, which is an availability gap in the isolation boundary.

**Fix (harness `tc-harness/0.2.0`).**
* Each grading container gets its own sandbox UID from 20000–59999.
  * The UID is held through an exclusive lock file while the container runs.
  * It is never a UID that a visible process already uses.
  * It has no passwd entry, so the sandbox environment sets `HOME`, `USER` and `LOGNAME`.
* In repository-test mode, a pytest run that exceeds its time limit is now recorded as
  `timeout` (the D28 limitation).
* Two regression tests were added to `tests/test_sandbox_isolation.py`:
  * the graded candidate starts at least 10 threads while another container holds 60
    threads as UID 1001;
  * concurrent UID allocations are distinct and skip UIDs in use.

  All 53 tests pass.

**Known limit (unchanged).** `RLIMIT_AS` = 1.5 GiB counts reserved address space.
glibc reserves a malloc arena per thread, so candidate code can start about 21
threads under the grader (measured). None of the pilot tasks needs more. It is
documented rather than changed, because it was not a cause of any observed error.

**Consequence (protocol §8).** This is a harness bug found after the pilot evaluation
started. The harness version is bumped and every condition of every task is re-run in
a new run, `pilot-v0.2-h2`.
* Run `pilot-v0.2` (harness 0.1.0; CS-03 and CS-04 complete) is kept unchanged as a
  superseded run. Its pair-by-pair agreement with the re-run is reported as a harness
  reliability measurement.
* Label proposals (D19) use the grader, so they are re-run under 0.2.0.
* audit:v1 records produced under 0.1.0 remain as recorded. They chose verifier
  revisions before freezing, and the frozen verifiers are unchanged.
* Remaining audits (CS-02 C4) run under 0.2.0.

### D30. Second resource-limit finding: address-space cap plus glibc arenas (open; fix before any further run)
Re-running the matrix under harness 0.2.0 (run `pilot-v0.2-h2`) showed the B1 run on
CS-04-eval-nm-1 stalling again. That run had passed in about 20 s under 0.1.0.

**Observed state of the stalled pytest process**
* single-threaded, sleeping in `futex_do_wait`;
* VmSize 1.4 GB, against the sandbox's `RLIMIT_AS` of 1.5 GiB;
* RSS only 65 MB.

**Likely mechanism (not yet proven by a dedicated probe)**
1. glibc creates a 64 MiB malloc arena for each thread that meets contention, up to
   8 × online CPUs, and never unmaps it.
2. Over a long multi-threaded test session, these reservations fill the address-space
   cap.
3. A later thread fails to start, and a test waits forever for it.

Arena creation depends on thread timing, so the failure is nondeterministic and
unrelated to the candidate. This is consistent with the about-21-thread capacity
measured in D29.

**Planned fix (harness 0.3.0)**
* Set `MALLOC_ARENA_MAX=2` in the sandbox environment, which bounds arena
  reservations.
* Add a Docker probe that churns threads and then starts many threads.
* Bump the version, then re-run every condition in a fresh run.

`pilot-v0.2-h2` was stopped after 4 pairs. It is kept as a superseded partial run.
Work paused at this point at the owner's request.

## 2026-11-18

### D30 (resolved 2026-11-18). Harness 0.3.0: bounded malloc arenas; per-UID process limit 256
**Mechanism confirmed.** A probe ran as candidate code under harness 0.2.0: 30
rounds of 32 allocating threads, then 60 waiting threads.
* Only 21 of 60 threads started, with VmSize 1,534 MiB, i.e. at the 1.5 GiB
  `RLIMIT_AS`. Each new thread costs a 64 MiB arena reservation plus an 8 MiB stack.
* With `MALLOC_ARENA_MAX=2` in the sandbox environment, all 60 started (VmSize
  567 MiB).

**Second limit.** The reference state's
`TestConcurrentTee::test_concurrent_consumers` (CS-04) starts 100 threads. The
sandbox UID's `RLIMIT_NPROC` of 64 then failed it on every candidate, including the
reference. Since D29 that UID is unique to one container. Fork-bomb containment
therefore rests on a per-container `RLIMIT_NPROC` of 256, below
`--pids-limit 512`, and the fork-bomb probe now asserts fewer than 256 forks.

**Harness `tc-harness/0.3.0`** = 0.2.0 + `MALLOC_ARENA_MAX=2` + `RLIMIT_NPROC` 256.
Regression probe `test_thread_capacity_after_churn` added. All 54 tests pass.
Previously stalling B1 pairs (CS-04 nm-1 and alt-1, two runs each) now complete in
about 40 s with no stall.

### D31. CS-04 B1 rebuilt as version 2 (selection was truncated by the harness bug)
Re-running B1's PASS-on-reference selection under 0.3.0
(`scripts/reselect_repo_tests.py`):
* CS-01, CS-02 and CS-03 keep identical selections (737, 239 and 466 checks).
* CS-04's frozen selection had 616 checks, from a reference run that aborted at the
  thread-heavy tests under harness 0.1.0. It included a spurious empty check id and
  missed 162 tests. Under 0.3.0, all 777 tests pass on the reference.

B1 for CS-04 is therefore version 2: same overlay (content hash unchanged), 777
checks, frozen. The previous selection is kept as `selection_v1.json`. The rebuild
is mechanical: the same overlay graded on the same reference candidate, with no
exposure to held-out candidates. Results from `pilot-v0.2` that used B1 v1 remain
superseded.

### D32. Protocol v0.3 timestamped before the final pilot run
`experiments/protocol.md` v0.3 written and hashed at 2026-11-18T08:42:06Z,
sha256 `348e0607c09e14c17360bcfdc113a0bb95aa42d0c1d239c70fcb8087d2e9d068`. At that time no evaluation run under harness 0.3.0 had been made.
The superseded runs `pilot-v0.2` (complete for CS-03/CS-04) and `pilot-v0.2-h2`
(4 pairs) existed and had been viewed. The exploratory construction-label analysis
(§11) was added after viewing them and is labeled exploratory.

### D33. Remaining held-out material, independent construction checks, second mappers (2026-11-18)
* **Generation.** Generated after every verifier of the task was frozen and run as
  workflow agents, under the same prompt templates as for CS-03/CS-04:
  * CS-01: five near misses (two earlier attempts were stopped; D30 note);
  * CS-02: two valid alternatives, five near misses and independent reference
    checks.

  Generator transcripts were audited with `scripts/audit_eval_generators.py`: CS-01
  `eval-nm`, CS-02 `eval-alt-1`, `eval-alt-2` and `eval-nm` all had 0 forbidden reads.
* **Construction checks (protocol v0.3 §11; advisory).** A second agent checked every
  held-out candidate of all four tasks in the sandbox against the reference:
  * 2 valid alternatives and 5 near misses per task;
  * the pre-correction states.

  The verdicts are in `tasks/*/labels/construction_checks.json`. They never change a
  label. Disagreements with D19 are queued for human review
  (`tasks/*/labels/review_queue.json`, which contains no verifier outcome). Notable
  disagreements:
  * CS-03 alternative 1 and the CS-03 pre-correction state diverge from the
    reference only on exotic Unicode input (modifier apostrophes, Turkish dotted İ),
    and are identical on all ASCII probes;
  * CS-02 alternative 2 fails read-after-write only when re-opening the file fails
    after the replace (read-only file or injected EMFILE);
  * the checker judges the CS-02 pre-correction state valid.
* **Second mapper.** An independent second model mapper, with the same instructions
  as mapper 1, mapped all four tasks. Agreement with mapper 1: κ = 1.0 on seven of
  the eight contract variants and 0.92 on CS-02 full-session. Both mappers are the
  same model, so this is not human agreement.
* **Asymmetry (deviation).** CS-02's reference checks, written last, also went through
  an independent review-and-fix loop before freezing: at most 2 fix rounds, validated
  only on the reference and the no-op. The reference checks of CS-01, CS-03 and
  CS-04 had been frozen and used for label proposals before this loop existed. They
  are not re-reviewed post hoc, because changing them after their labels were seen
  would contaminate the labels.

### D34. Contribution claim narrowed to a conjunction after adversarial verification (pending owner confirmation)
The brief-verification workflow (2026-11-13 close reading; 2026-11-18 fresh search,
citation check, fact check and revision; `docs/research/review_*.md`) found partial
precedents for every component of D25:
* SessionFarmer (Table 3) already scores initial and refined suites on one held-out
  rollout pool. It reports false-positive and false-negative rates against LLM
  labels.
* traj2envs and ARE-bench use the agent's earlier states, but only as
  construction-time material.
* Human-labelled grader errors exist for LLM judges.

The claim is therefore limited to the conjunction of:
1. verifiers generated by one frozen procedure from initial-request-only versus
   correction-aware contracts;
2. one frozen held-out pool anchored on the session's own user-rejected
   pre-correction states, with independent alternatives and near misses;
3. independent human labels.

The with/without-audit comparison, correction-aware statements, held-out verifier
scoring and two-sided metrics are cited as prior work. Because element 3 does not
exist yet, the current pilot can make descriptive statements only. D25 is not
edited, since the log is append-only. The narrowed wording is used in the
manuscript (`paper/sections/related.tex`, introduction) and awaits the owner's
confirmation (brief §8 item 4).

### D35. Harbor export uses a per-run sandbox UID; re-validated under harness 0.3.0
The Harbor grade script (`harbor_export.GRADE_PY`) ran candidate code as the fixed
UID 1001. That is the D29 coupling, in case Harbor runs trials concurrently on one
host. It now draws a UID from 20000–59999 for each run. Inside a container a
host-wide check is not possible; a random UID from a large range makes a collision
unlikely.

Re-validated with Harbor 0.25.0 on the synthetic fixture task (population
`fixture`, not evidence), re-exported with harness 0.3.0:
* `harbor lint` rc=0;
* oracle with `CANDIDATE=reference`: reward 1.0;
* oracle with the wrong candidate: 0.0;
* `nop`: 0.0.

As before, the trials used the `local-validation` network variant (D20).

### D36. Harness 0.3.1: candidate code cannot replace the wrapper's own modules (internal review SEC-1/SEC-2)
The adversarial internal review (2026-11-18, security lens) showed a forging channel in
the process-separated grader. Docker proof: a wrong candidate received reward 1.0.
* **Shadowing.** Sandbox children started with the candidate directory on `sys.path`
  ahead of the standard library. A candidate `json.py` therefore replaced the
  serialiser of the trusted wrapper, which then signed the forged payload with the
  real per-call key.
* **Runtime hooks.** A `sitecustomize.py` written to `/work` at runtime ran in every
  later call. The patch filter is static and cannot stop runtime writes.
* **Script directory.** A shadow in `/tmp` was exposed through the wrapper script's
  directory.

**Fix (`tc-harness/0.3.1`).**
1. Children start with `-s -S -P`.
2. The wrapper removes the candidate directories from `sys.path`, runs `site.main()`
   and imports `os`, `json`, `hmac`, `hashlib` and `traceback`.
3. Only then does it put the candidate directories back, for the snippet.

Two Docker regression probes were added (a forging `json.py` shadow; startup hooks
planted in `/work`, `/tmp` and the user site). Both fail under 0.3.0 and pass under
0.3.1.

**Scope.** The honest-candidate pilot results are not affected: the wrapper's
behaviour for code that does not attack it is unchanged. Under §8 every condition is
still re-run under 0.3.1 (run `pilot-v0.3.1`). Within one call, candidate code still
controls what it reports, for example by detecting the grading environment. That
remains a documented limitation. B1 runs in-process and is not covered by this fix
(it is forgeable; D37).

### D37. Integrity disclosures and exploratory analyses from the internal review
**Integrity disclosures.** Verified against git history and the agent transcripts.
* **Duplicates of a dev attack.** Two CS-04 held-out candidates have the same graded
  patch as development attack `CS-04-dev-attack-full_session-a3`, which C4's audit
  used: `CS-04-pre-correction` (the anchor negative) and `CS-04-eval-nm-2`. CS-04's
  C4 audit made no revision (C4 = C3), so the verifier's tests did not change because
  of it. The pool still double-counts one behaviour, and the C4 audit was not blind to
  it.
* **B1 tests in near-miss workspaces.** Near-miss workspaces were exported with the
  full reference diff, which includes the reference state's test files. Those files
  are B1's tests, and the generators ran them before registering their near misses.
  B1's outcomes on near misses are therefore not blind to construction.
* **Reference-check timing.** The independent reference checks of CS-01 and CS-04
  were written while the held-out pool was being generated; their writers had no
  access to it (audited). CS-02's were written after the pool existed. The evaluated
  verifiers (C1–C4, B1 v1, B2) were all frozen before any generated held-out
  candidate existed. B1 v2 for CS-04 is the exception (D31).
* **Near-miss prompt change.** The near-miss prompt used for CS-01 and CS-02 added the
  repository-test command and "finish one near miss before the next", relative to
  CS-03 and CS-04 (`experiments/prompts/`).
* **Audit limits.** Generator audits inspect tool *inputs* only. Some tool outputs,
  such as a `git status` listing, showed held-out file names to fix agents. Agents
  also shared a scratch directory.
* **Content hash.** The verifier content hash covered test files only. Specs now also
  record `checks_sha256` (backfilled for all 28 frozen specs; D36 commit) and
  `frozen_at` for new freezes.

**Exploratory analyses added after the review (not pre-specified; never primary):**
* near-miss acceptance by D19 status;
* rates under the independent construction checks' labels;
* rates without the duplicated candidates;
* B1 restricted to checks that exist in the base commit's own tests
  (`scripts/b1_upstream_checks.py`). B1 includes 6–12 tests per task that the session
  agent added.
* exact (Clopper–Pearson, unclustered) intervals next to the cluster bootstrap, with
  degenerate bootstrap intervals flagged;
* macro rates in every output;
* per-metric denominators in the paired comparisons;
* "covered but contradicted" in contract coverage.

**Reliability comparison.** It now separates pairs whose verifier changed between
runs.

### D38. Transcript sanitiser v2
* **Diff decorators.** The e-mail pattern matched diff decorator lines (`+@pytest...`),
  corrupting two published diffs. It no longer does: a local part needs a letter or
  digit after leading diff markers.
* **Opaque fields.** Content-block `signature` and `caller` fields are dropped.
* **Harness messages.** These are marked `isMeta`. Their content is replaced, but the
  line is kept so event ids stay stable. The scripted user turn, delivered as a meta
  message, is kept.

All four transcripts were re-sanitised from the raw source with `sanitize:v2`:
* line counts and user turns are unchanged;
* `validate-task` passes;
* one real e-mail address per transcript is redacted.

The provenance records carry the new hashes; the previous ones are kept. The CS-02
record had wrongly said `not_needed_controlled` and lacked its sanitisation record;
both are fixed.

### D39. Re-run under harness 0.3.1 and protocol v0.4
Protocol v0.4 (§12) records the D36–D38 changes. It was written and hashed before
re-proposing labels and re-running the full matrix under 0.3.1 as `pilot-v0.3.1`.
`pilot-v0.3` (harness 0.3.0) is kept and compared pair by pair.

Protocol v0.4 written and hashed at 2026-11-18T11:58:51Z, sha256 `70ffee9a56b2f676df1d0a2606a824e345bec02f91ce3878a3ea7755c5d7adec`, before the 0.3.1 label re-proposal and run.

**Labels re-proposed under 0.3.1** (2026-11-18, 11:59–12:06 UTC, `scripts/propose_labels.py`, all four tasks). All 32
D19 proposals match the 0.3.0 proposals: same value, same violated requirements and same recorded
reference-check and regression outcomes. In the 36 label files (32 candidate records and 4
`proposed_labels.json`), only the timestamp line changed.

**Harbor export re-validated under 0.3.1** (2026-11-18). The export bundles the grading harness, so the
D35 validation (0.3.0) no longer covered it. `scripts/harbor_validate.sh` with Harbor 0.25.0 on the
synthetic fixture task (population `fixture`, not evidence; exported harness `tc-harness/0.3.1`):
`harbor lint` rc=0; oracle with `CANDIDATE=reference` 1.0; oracle with the wrong candidate 0.0; `nop` 0.0.

**Result of the re-run.** `pilot-v0.3.1` graded all 240 pairs under `tc-harness/0.3.1` in one invocation
(2026-11-18, 12:18:50–12:34:52 UTC) at revision `c830977`, with no infrastructure outcomes. It agrees with
`pilot-v0.3` (harness 0.3.0) on all 240 pairs, in reward and in exact outcome. Every number in the analysis
is identical; only metadata differs (harness version, input-file hashes). Compared with the superseded runs:
`pilot-v0.2` agrees on all 99 pairs whose verifier is unchanged and on 8 of the 9 changed CS-04 B1 pairs.
`pilot-v0.2-h2` has only 4 pairs, all graded with the earlier CS-04 B1 selection, and agrees on all 4.

### D40. Dispositions review, final claims audit, harness 0.3.2 and protocol v0.5
**Reviews (model agents, read-only; not human review).**
* **Dispositions review** (workflow `tracecontract-review-dispositions`, 12:19–13:46 UTC).
  For each of the 64 internal-review findings, one agent per lens group recorded how it
  had been resolved, and a second agent tried to show that disposition wrong. Result:
  23 fixed, 33 partly fixed, 5 disclosed, 3 fixed and disclosed. The checker corrected
  29 dispositions. The remaining items are addressed below, in D41 and D42, or listed
  as open in `docs/internal_review.md`.
* **Final claims audit** (workflow `tracecontract-final-audit`). Four lenses: numbers,
  procedure, consistency and reproducibility. Each finding was checked by a verifier
  agent, and a critic looked for gaps. Findings the verifiers confirmed are fixed in
  the same change as this entry.

**Harness 0.3.2 (`tc-harness/0.3.2`).** The D36 fix was incomplete: sandbox children
still started with the candidate directory on `PYTHONPATH`. The interpreter imports
the `encodings` package from `sys.path` while it starts, before the wrapper's first
line. A candidate `encodings` package could therefore run before the trusted imports
and redirect them. It could be shipped in the patch (`encodings/` is not a protected
path) or written to `/work` at runtime.

Docker proof under 0.3.1: a wrong candidate that ships `encodings/__init__.py`, which
puts a forging `json.py` on `sys.path`, received reward 1.0. A runtime-written
`/work/encodings` loaded at the start of the next call.

The fix: `run_python` children start without `PYTHONPATH`. The wrapper restores it in
`os.environ` and puts the candidate directories on `sys.path` after its trusted imports.

Equivalence check: under both candidate-path layouts used here (`/work` and
`/work/src:/work`), a snippet sees the same `sys.path`, `PYTHONPATH`, interpreter flags,
loaded modules and environment under 0.3.1 and 0.3.2. Both probes fail under 0.3.1 and
pass under 0.3.2 (`tests/test_sandbox_isolation.py`).

The repository-test baseline (B1) now keeps the pytest output tails in the host logs.
Before, its log files held only a separator. Within one call, code imported by the
snippet still controls what that call reports (the documented in-call limit), and B1
remains in-process and forgeable (D42).

**Third duplicate.** Held-out near miss `CS-01-eval-nm-5` differs from development
attack `CS-01-dev-attack-full_session-a3`, which C4's audit used, by one docstring
line. CS-01's C4 audit made no revision (C4 = C3), so the overlap did not change C4's
tests.

`scripts/find_duplicates.py` now records same-code duplicates (comments and docstrings
ignored; Python compared by syntax tree) in `tasks/*/labels/duplicates.json`. It finds
no others in the four tasks, and the preflight check fails if the record is out of date.

**Protocol v0.5** (§13) records these changes and corrections of wording. It was
written and hashed at 2026-11-18T14:12:50Z, sha256
`3fa9d843cf5d53013e17e8e66f457eb684c5da9127b687612dfbf0bc1ff02aa0`, before the 0.3.2
label re-proposal and run.

**Labels re-proposed under 0.3.2** (2026-11-18, 14:16–14:24 UTC, `scripts/propose_labels.py`,
all four tasks): all 32 D19 proposals are identical to the 0.3.1 proposals; in the 36 label
files only the timestamp line changed.

**Final run `pilot-v0.3.2`** (2026-11-18, 14:24:59–14:40:41 UTC, revision `0a94529`, one
invocation): 240 pairs under harness 0.3.2, no infrastructure outcomes. It agrees with
`pilot-v0.3.1` and `pilot-v0.3` on all 240 pairs, in reward and in exact outcome, so every
reported number is unchanged except the exploratory duplicates view (now three candidates).
Against `pilot-v0.2` the 99 pairs with an unchanged verifier agree, and 8 of the 9
changed-verifier pairs; the 4 `pilot-v0.2-h2` pairs all have a changed verifier.

**Harbor export re-validated under 0.3.2** (2026-11-18), from the tracked fixture snapshot:
`harbor lint` rc=0; oracle with `CANDIDATE=reference` 1.0; oracle with the wrong candidate 0.0;
`nop` 0.0. The outputs are recorded in `results/harbor_validation/tc-harness-0.3.2/`. The export
step also ran from a fresh clone. After the run, 70 tests pass (54 offline, 16 Docker).

**Older reports.** The HTML reports of `pilot-v0.3` and `pilot-v0.3.1` predate the output
changes above: they show no macro rates, exact intervals, degenerate marks, per-metric
denominators or "covered but contradicted". Protocol v0.4 §12 was met there only by
`analysis.md` and the paper tables. Recorded outputs are not edited; `results/runs/README.md`
marks the superseded runs.

### D41. Corrections to earlier entries (found by the reviews of D40)
The log is append-only, so earlier entries are corrected here. The one non-append
edit is the `## 2026-11-18` heading inserted before D30 (resolved). Entries from there
to D39 were written on 2026-11-18 but sat under the 2026-11-13 heading.
* **D5, D10, D11 ("registered", "pre-registered").** These mean hashed and logged
  locally before the session, not a formal preregistration (D15).
* **D11 ("exact evidence quotes").** One reference requirement, CS-04
  `R-default-unchanged`, is inferred and has no quote. The same holds for the
  frozen protocol text (§5).
* **D11, D12, D26 ("ground truth").** This means the sealed reference material
  (scenario, reference proposals, reference contract), the study's labeling standard.
  The study's AI agent wrote the scenarios and the reference operationalisations before
  each session. It is the same model as the session agent. So far only a model has
  reviewed them, and no human has written or reviewed them. The legacy proposer label
  `study-design:pre-registered` in `tasks/*/contracts/reference.json` has the same
  meaning. New builds write `study-design:hashed-scenario`.
* **D14, D37 (held-out separation).** Generators and reference-check writers ran as the
  same user (root) in the repository checkout. Frozen verifiers, the reference patch
  and registered candidates were therefore readable, and the near-miss workspaces also
  held B1's test files (D37). Separation rested on instructions and on the tool-input
  audit, which found no forbidden read. "Had no access" in D37 should read "no
  recorded read". The pre-correction state was captured during the session, before
  any verifier existed. B2's generator and the full-session contract proposer saw its
  edits, abbreviated, in the session text. CS-04's B1 was re-selected after its pool
  existed (D31).
* **D26.** Agents ran as uid 0, so the mode-0700 directory was no barrier. The
  2026-11-18 held-out prompts name it in their do-not-read list.
* **D21.** The counts were wrong (D38). CS-01 had one address plus one diff decorator
  that was wrongly redacted and restored in `sanitize:v2`. CS-02 had one address,
  which D21 did not list. CS-03 and CS-04 had one each.
* **D33.**
  * The 2026-11-18 held-out prompts were not "the same prompt templates as for
    CS-03/CS-04". The shared preamble gained a working-style line, "tool outputs" in
    the data-not-instructions line, a different owner-context note and a longer
    do-not-read list. The near-miss steps gained the repository-test command, a
    one-at-a-time instruction and a package-path hint. The alternative and
    reference-check steps changed too, the reference-check prompt most.
  * Stopped attempts: besides the two CS-01 near-miss attempts, four CS-02 agents
    (alternatives, near misses, reference checks, a mapper) were started on
    2026-11-13 and stopped at the D30 pause. They ran only inspection commands and
    registered nothing. These six transcripts were not audited. The prompt export
    marks them (`experiments/prompts/agent_prompts.jsonl`, field `note`).
  * CS-03 alternative 1 diverges from the reference on modifier apostrophes (U+02BB,
    U+02BC) and on 98 ASCII probes, all apostrophe-joined tokens. The CS-03
    pre-correction state diverges only on non-ASCII all-caps input (Turkish dotted İ,
    circled capitals) and matches on all 5,479 ASCII all-caps probes. D33 said both
    were identical on all ASCII probes.
  * Mapper 2 (all tasks) and mapper 1 for CS-02 got one extra sentence: they cannot
    run code, so a contradiction claim that depends on what the base code outputs must
    be flagged in the note, not asserted. It was added after the CS-01 mapper-1
    correction (D42). The agreement in D33 is therefore between slightly different
    instructions.
* **D37 (reference-check timing).**
  * CS-01 and CS-04: written while their pools were being generated.
  * CS-02: its writer wrote its test files at 08:48–08:52 UTC, before the first CS-02
    candidate was registered (08:53). The review-and-fix rounds ran 09:13–10:20, mostly
    after the pool was complete (09:18), and the checks were frozen at 10:21
    (`fe30c15`). D37 said "after the pool existed".
  * CS-03: frozen (`07bdd71`, 04:01) before its pool was registered (04:06–04:12).
* **D37 (audit limits).** The shared scratch directory held held-out material, and the
  third CS-02 reference-check reviewer listed it (10:12 UTC). The listing showed a
  held-out file name (`CS-02-eval-alt-1`).
* **D36.** "(it is forgeable; D37)" should point to D42. The fix did not cover start-up
  imports (D40).
* **D39.** The label re-proposal ran 11:59–12:07 UTC (last label 12:07:24), not
  11:59–12:06.
* **Protocol v0.5 §13** (already hashed) should say that mapper 2 (all tasks) and mapper 1
  for CS-02 got the extra sentence, and cite D41 rather than D40 for it.

### D42. Records the log lacked
* **B1 forgeability probe** (commit `18e4878`, 2026-11-18T08:53:54Z):
  `tests/test_sandbox_isolation.py::test_in_process_repo_tests_report_is_forgeable_known_limitation`.
  An honest wrong candidate fails B1. A candidate whose `atexit` hook rewrites the
  JUnit report passes. This is a documented limitation of the in-process baseline.
* **CS-01 mapping correction** (commit `d7a3e02`). The builder changed mapper 1's
  `contradicts.R9` in `tasks/CS-01/contracts/mapping_full_session.json` from
  `[R-opt-in]` to `[]` (field `corrections`). The mapper, which could not run code, had
  assumed that the base renders `naturalsize(999999)` as `1000.0 kB`. In the sandbox
  it renders `1.0 MB`, which is consistent with R9's assertion. Effect on the coverage
  table: CS-01 full-session "Contradicting" goes from 1 to 0 and "covered but
  contradicted" from 1 to 0. Coverage is 4/4 either way.
* **CS-02 audit outcomes.** C2 needed 0 revisions and is identical to C1. C4 needed
  1 revision. All audit outcomes are now in the generated verifier table
  (`paper/generated/verifiers_table.tex`).
* **Costs not recorded (deviation from protocol §6).** Generation cost per condition
  and per accepted task was not recorded and is not reported. The verifier specs'
  generation fields (`run_id` "unrecorded", empty `prompt_sha256` and budget) were
  never filled. The prompts are exported separately (`experiments/prompts/`) and are
  not linked from each spec.

### D43. Blinded review packet for human labels; findings of the audit's completeness critic
The completeness critic of the final claims audit (D40) found that the annotation guide
was not blind. It sent reviewers to the review queue and the candidate files, which show
each candidate's origin, the generator's description, the construction label and the
rule's proposal. The candidate ids give the origin away as well. Human labels, the
missing element of the claim (D34), would have been anchored on construction intent.

**Fix.** `tracecontract review-packet` writes a packet per task (`src/tracecontract/review.py`):
* the rendered session;
* the reference contract;
* each held-out candidate's graded diff and file state, under random ids, in shuffled
  order, with no candidate id, origin, description, proposal, check or verifier outcome.

The key that maps ids to candidates goes to a separate file kept by a coordinator.
`tracecontract merge-reviews` refuses to merge until every task has two complete
reviews. It then appends the labels as human labels and lists the disagreements for
adjudication. The annotation guide (v0.3) has reviewers work only from the packet and
open the queue and the recorded evidence only after the merge.
`tests/test_review_packet.py` checks that no id, origin or description leaks into the
packet. No candidate patch in the pool contains comments that reveal its origin.

**Other critic findings.**
* **Model identities.** The session agent's model is recorded in every assistant entry
  of the published transcripts. The other agents' model identifiers are not in the
  repository. The paper and the data card now say so.
* **Older run outputs.** The superseded runs are now marked
  (`results/runs/README.md`, `SUPERSEDED.md` in each folder); the older HTML reports'
  gaps are recorded in D40. The HTML report embeds the upstream licence notices.
* **Wording of protocol v0.5 §13** on the mapper instruction: corrected in D41.
* **Implementation claims** checked against the code, and **related-work numbers**
  checked against the primary papers: no problem found.

### D44. Verification of the D40–D43 fixes; harness 0.3.3; stricter generator re-audit; protocol v0.6
**Verification (model agents, read-only; not human review).** Workflow
`tracecontract-fix-verification` (run `wf_647ff2b0-8cb`, 2026-11-18, 14:51–17:07 UTC).
Four lenses (paper; documents; code; diff and privacy) read the changes made since the
D40 reviews. A second agent tried to refute each finding, and a critic looked for gaps.
Result: 72 findings (26 medium, 46 low), 68 confirmed and 4 refuted. The confirmed ones
are fixed in this change or in the text corrections that follow it; any left open are
listed in `docs/internal_review.md`.

**Harness 0.3.3 (`tc-harness/0.3.3`).** The 0.3.2 fix (D40) left an import path into the
trusted code. After its trusted imports, the wrapper puts the candidate directories on
`sys.path`. When a snippet raised, the wrapper's own error path then imported modules
lazily: Python 3.12's `traceback` imports `ast` (caret positions) and `unicodedata` while
formatting a traceback. A candidate `ast.py`, shipped in the patch or written at runtime,
therefore ran inside the code that signs the result, even when the snippet imported no
candidate module.

Docker proof (`tests/test_sandbox_isolation.py::test_error_path_lazy_import_cannot_forge_results`):
with a candidate `ast.py` planted, the snippet `result = 1 / 0` was reported under 0.3.2
as `ok=True` with a forged value. Under 0.3.3 it is reported as `ok=False`,
`ZeroDivisionError`.

The fix:
* `ast`, `unicodedata`, `linecache` and `tokenize` are imported with the trusted modules.
* As soon as the snippet returns or raises, the wrapper puts back its own `sys.path` and
  `sys.meta_path` (new list objects) and clears `sys.path_importer_cache`. Only then does
  it format, serialise and sign anything.
* Relative or empty `PYTHONPATH` entries are now resolved against the child's working
  directory, as the interpreter resolves them. 0.3.2 resolved them against the grader's
  working directory. No task uses such an entry.

The in-call limit is unchanged. Code that the snippet runs, directly or through candidate
modules it imports, can still change what that call reports.

No candidate patch in the pool ships a module named `ast`, `unicodedata`, `linecache`,
`tokenize`, `traceback`, `encodings`, `json`, `hmac`, `hashlib`, `os` or `sys`.

Equivalence check (2026-11-18, Docker): under all three candidate-path layouts (`/work`
for CS-02–CS-04, `/work/src` for CS-01, and `/work/src:/work`), a snippet sees the same
`sys.path`, `PYTHONPATH`, interpreter flags and environment under 0.3.2 and 0.3.3. The
only difference is that `ast`, `_ast` and `unicodedata` are already loaded. The same
check of 0.3.1 against 0.3.2 gives identical views under all three layouts. This corrects
D40, which named `/work/src:/work` (used by no task) instead of CS-01's `/work/src`.

**Stricter re-audit of the generator transcripts.** The tool-input audit (D26, D37)
matches substrings of the paths an agent passed to its tools. `scripts/strict_reaudit.py`
(using `controlled.audit_generator_transcript_strict`) resolves them instead:
* it splits shell commands into segments and skips heredoc bodies;
* it follows `cd` and substitutes variables set earlier in the same command;
* it honours `find -prune`;
* it also resolves relative paths from the directory an earlier call ended in.

It flags reads inside forbidden material, and recursive searches or listings whose root
contains forbidden material. The script finds each recorded transcript by its sha256. It
writes a `strict_reaudit` block into every record of `tasks/*/labels/generator_audit.json`
and keeps the original record. All 21 transcripts were re-audited: the 12 held-out
generators, the CS-01, CS-03 and CS-04 reference-check writers, and CS-02's writer with
its three reviewers and two fixers. Each assessment comes from reading the transcript,
tool outputs included.

The re-audit found an audit gap. The held-out generators, the reference-check writers
and their reviewers ran as subagents of the build session. They shared its scratch
directory with the builder and with each other, and many of them wrote their helper
scripts there. The first audit treated only the sealed subfolders of that directory as
forbidden. The rest held other agents' working files and some material derived from
candidates:
* the patch of `CS-04-eval-alt-1`, which the builder extracted there on 2026-11-13 at
  04:15 UTC;
* outputs that the independent check agents wrote for registered candidates, for
  example `CS-02-eval-alt-1.json` (from 2026-11-18, 08:55 UTC).

The re-audit therefore treats the whole scratch directory as forbidden. It attributes
each read there to the agent that last wrote the file, using a write index built from
every transcript of the session, the builder's included.

Result: no audited agent read forbidden material. Listings that showed names only:
* the generator of CS-02's near misses listed the top level of the scratch directory
  once (08:55 UTC);
* the third reviewer of CS-02's reference checks listed it once (10:12 UTC, already in
  D41);
* the second fixer of CS-02's reference checks listed `~/gen_workspaces/CS-02/`. This
  corrects the first assessment's statement that no tool input of that chain names an
  agent workspace;
* the CS-03 and CS-04 reference-check writers listed `tasks/<id>/verifiers/` (D27).

Besides listings, the third CS-02 reviewer read the first 50 lines of the first
reviewer's test runner. That runner imports the four reference-check test modules and
prints PASS or FAIL, and it is outside the read-only list in the reviewer's prompt; it
holds no candidate or other verifier material. Every other read in the scratch directory
was of a file the reading agent had written. The remaining automatic flags are parser
limits, each explained in its record:
* files created by the agent's own inline code;
* redirects inside quoted commands;
* `cd` to a directory named with a variable.

The checks still do not read tool outputs, and paths that inline code builds at run time
are matched only by name. `tests/test_generator_audit.py` covers the parser. The
preflight check now fails if a record lacks an assessed strict re-audit.

**Human-label procedure** (not yet used; protocol v0.6 §14). The verification found that
the D43 packet hides the origin field but not the origin. The user's corrections describe
the agent's first attempt. Near misses resemble each other and the reference, and in
CS-02 the diff structure differs by origin. Packet changes:
* `session.txt` holds the user turns only.
* Candidates with identical diffs share one id.
* Ids are drawn from `secrets.token_hex(3)`. The shuffle stays seeded.
* The key file is created with `O_EXCL` and mode 0600.
* State directories are made readable for the sandbox user (mode 0755).
* The template is named `label_template.json`, so the merge's file pattern does not
  match it.
* Reviewers use pseudonymous ids (`R1`, `R2`, …), which the merge enforces.
* Each reviewer records a contract review and an origin guess per candidate. The merge
  reports how often the guesses are right.
* The packet README's do-not-open list now also names `docs/`, `README.md`, `STATUS.md`,
  `experiments/`, the HTML reports, `validate-task --show-candidates` (candidate details
  are now hidden by default) and the git history.

Rules for merging and labels:
* Every task is reviewed by two reviewers. The merge requires two complete reviews per
  task and refuses to merge the same packet twice.
* An "invalid" label must name a scored requirement or `REGRESSION`.
* `Candidate.final_label()` gives no label while the latest human labels disagree and no
  adjudication exists. Before, it took the last reviewer's label. `analysis` lists such
  candidates as needing adjudication.

**Pre-push scan.** `scripts/scan_tracked_files.py` now also scans every file version in
the commits a push would send (`@{upstream}..HEAD`; `--all-history` scans all of
history). A file added in one commit and removed in a later one is still published by the
push. `--private-markers` takes the redaction file kept outside the repository. The scan
is a manual step before each push, not a git hook. Results on 2026-11-18:
* pending commits: no finding;
* whole history: 99 findings, all in already-disclosed history (STATUS lists the commits).
  Rewriting history is the owner's decision.

**Corrections to earlier entries.**
* **D40 (outputs not edited).** No raw result, manifest, analysis or report of a
  superseded run was edited. The run-comparison files in the superseded run folders were
  regenerated on 2026-11-18 with the current `scripts/compare_runs.py` (commit `55a2346`).
* **D40 (v0.5 timing).** Protocol v0.5 was hashed (14:12:50 UTC) after the final claims
  audit had found and verified its findings. The audit's completeness critic finished at
  14:36 UTC, after the hash and after `pilot-v0.3.2` had started (14:24:59 UTC). Its
  findings (D43) changed no analysis, label rule or graded input.
* **D41 (non-append edits).** Besides the `## 2026-11-18` heading, D5 (in `cbb8dcd`) and
  D40 and D41 (in `55a2346` and `45c654c`) were extended after their first commit. No
  line of the log has been removed. Later additions go into new entries.
* **D41 (stopped attempts).** Seven agents were stopped at the D30 pause, not six: the
  two CS-01 near-miss attempts and five CS-02 agents. The CS-02 agents were alternative 1,
  alternative 2, the near misses, the reference checks, and the mapper
  `af91f45e0c716a5a2`, which ran 04:30–04:34 UTC on 2026-11-13. The prompt export now
  marks all seven. CS-02's mapper-1 files come from the 2026-11-18 held-out workflow
  (`tracecontract-heldout`, run `wf_b428f318-391`, agent `a98177684c912c810`,
  08:39–08:52 UTC).
* **README, data card and paper (reference-check timing).** These said that CS-03's
  reference checks were written "just before" its pool. The writer ran
  03:45:36–03:57:26 UTC on 2026-11-13, alongside the three CS-03 generators
  (03:45:36–04:12). The checks were frozen (`07bdd71`, 04:01) before the pool was
  registered. D41 is accurate.
* **README, data card and paper (prompts).** These said the prompts of the families
  generated last differ. The 2026-11-18 prompts are CS-01's near-miss prompts and all of
  CS-02's prompts for held-out candidates and reference checks. CS-01's alternatives and
  reference checks used the CS-03/CS-04 prompts, as D41's list implies.

**Protocol v0.6** (§14) records these changes. It was written and hashed at
2026-11-18T17:43:44Z, sha256
`c70a26ebfb1fac57cb11bc254985fa1d7f3ee29082e2705e7838be4cdc5f766d`, before the 0.3.3 label
re-proposal and run.

### D45. Re-run under harness 0.3.3 and protocol v0.6; text corrections; corrections to D44
**Labels re-proposed under 0.3.3** (2026-11-18, 17:47–17:56 UTC, `scripts/propose_labels.py`,
all four tasks, commit `5cb8d95`): all 32 D19 proposals are identical to the 0.3.2 proposals;
in the 36 label files only the timestamp line changed.

**Preflight.** Its new strict re-audit check (D44) first failed with an exception: it read
the `_rules` entry of `generator_audit.json` as a record. The fix (`c997779`) only skips that
entry. The run started from that commit.

**Final run `pilot-v0.3.3`** (2026-11-18, 17:56:44–18:11:58 UTC, revision `c997779`, one
invocation): 240 pairs under harness 0.3.3, no infrastructure outcomes.
* It agrees with `pilot-v0.3.2`, `pilot-v0.3.1` and `pilot-v0.3` on all 240 pairs, in reward
  and in exact outcome, so every reported number is unchanged.
* Against `pilot-v0.2`, the 99 pairs with an unchanged verifier agree, and 8 of the 9
  changed-verifier pairs. The 4 `pilot-v0.2-h2` pairs all have a changed verifier.
* The comparison files are written to the new run's folder only. No file of an earlier run
  was regenerated. `pilot-v0.3.2` is marked superseded (`SUPERSEDED.md`, `results/runs/README.md`).
* The analysis, report, paper tables and evidence ledger were regenerated from it (`fe5cc50`).
  Only run names and two captions changed: the duplicate count now comes from the analysis,
  and the reliability caption names the check-list criterion.

**Harbor export re-validated under 0.3.3** (2026-11-18, 18:12–18:14 UTC, `feab025`), from the
tracked fixture snapshot. Results:
* `harbor lint` rc=0;
* oracle with `CANDIDATE=reference`: 1.0;
* oracle with the wrong candidate: 0.0;
* `nop`: 0.0.

The outputs are in `results/harbor_validation/tc-harness-0.3.3/`. The export step also ran
from a fresh clone.

**Text corrections.** Workflow `tracecontract-text-corrections` (run `wf_d90a88d4-3c3`,
17:58–19:36 UTC). The confirmed text findings of the verification (D44) went to six batches
of disjoint files:
* the paper core;
* the paper's front matter and appendix;
* the annotation guide and governance notes;
* the data documents;
* the research brief;
* README and STATUS.

For each batch, one agent edited a separate git worktree. A second agent then checked the
edits against the sources. It reported 29 issues (two medium, the rest low) and corrected 25
of them, all errors of precision or scope. Of the other four, one needed no change and three
were left to the builder: a medium one (the blinding gap below) and two run-dependent updates. The builder
read the result and applied it to the checkout. The builder then made the run-dependent
updates (run names, harness versions, counts), which the editors had been told to leave.

The reviewers also raised points outside their batches, which were handled as follows:
* **A blinding gap.** `data/controlled/transcripts/` holds the full sessions, including the
  agent's edits before the correction. Neither the packet README nor the guide told reviewers
  to stay out of it. Both lists now name `data/`.
* **A missing test.** Nothing checked that the packet's session text holds only user turns.
  `tests/test_review_packet.py` now does, with a synthetic transcript.
* **Stale version mentions.** Three code files still named annotation guide v0.3. They now
  say v0.4, the guide's new version.
* **The history list.** STATUS's list of removed material still in pushed history gave the
  redaction rules for `c830977` only. They are in `scripts/export_prompts.py` from `c830977`
  to `74f6c73`, and one of them is built from part of the build session's id.

`docs/internal_review.md` gains a section on the verification of the fixes, with a
disposition for every finding and critic area. The Method section now says "six others"
(methodology L7–L10, reproducibility R9 and R10) where it said "three others".

**Review procedure checked end to end** (2026-11-18, in the scratch directory; nothing
recorded). `review-packet` for CS-01 and CS-03 wrote:
* a key file with mode 0600;
* state directories with mode 0755;
* a session text with the user turns only.

`sandbox-python` ran in a packet state directory. The documented merge command
(`<packet>/*/labels_*.json`, dry run) did not match the templates. It reported the
disagreements of two synthetic reviewers. It refused a reviewer named by a real name, and an
"invalid" label that cites a superseded requirement.

**Corrections to D44.**
* **Outputs of superseded runs.** D44 said that no raw result, manifest, analysis or report of
  a superseded run was edited, and D40 said that recorded outputs are not edited. Both are
  wrong for derived files. No raw result or manifest of any run was edited. But:
  * `47b15ad` (2026-11-18, 08:49 UTC) added sections to `pilot-v0.2`'s analysis, after D29
    had declared that run superseded;
  * `c9065d1` and `8c13e0c` (10:44 and 11:58 UTC) regenerated `pilot-v0.3`'s report, its
    analysis and its comparison with `pilot-v0.2` shortly before it was superseded;
  * `55a2346` regenerated the comparison files of `pilot-v0.3` and `pilot-v0.3.1`.

  Git keeps every earlier version, and `results/runs/README.md` and the `SUPERSEDED.md` files
  now state this.
* **Assessments.** "Each assessment comes from reading the transcript, tool outputs included"
  holds for the accesses the script flags. The assessments of records without flags restate
  the script's classification. The `_rules` text of the four `generator_audit.json` files
  now says so; these files are not inputs of the analysis.

**Tests.** After these changes, 76 tests pass (59 offline, 17 Docker).

### D46. Final verification of round 3; hardened re-audit; corrections to D44 and D45
**Verification (model agents, read-only; not human review).** Workflow
`tracecontract-round3-verification` (run `wf_86ad51e6-055`, 2026-11-18, 19:47–21:46 UTC).
It covered everything changed from `45c654c` to `aa41b45`. Four lenses (records;
consistency of the public text; code; the re-audit records against the transcripts),
one skeptic per lens and a critic. Result: 27 findings (11 medium, 16 low), all
confirmed; the critic added 6 more. The dispositions are in `docs/internal_review.md`.

**The stricter re-audit, hardened.** The verification showed that the D44 re-audit
missed several shell forms and dropped accesses to the scratch directory itself:
* the parser split at `|` and `;` inside quotes and treated `VAR=x cmd` as an
  assignment;
* it ignored subshells, loops, command substitutions, wrappers such as `env` or
  `timeout`, every `find` root but the first, long recursive options and git listings;
* it exempted any segment that contained the text `tracecontract add-candidate`;
* `scripts/strict_reaudit.py` kept only listings of the scratch directory's top level,
  dropped searches, reads and inline code given its path, and attributed recursive
  reads inside it like single files.

The strict audit now splits only at unquoted operators and follows those forms. It
also applies the first audit's substring rule and flags every literal forbidden path
named anywhere in a tool input, so it flags at least what the first audit flags. The
script lists every access to the scratch directory itself and attributes recursive
reads by the listing rule. `tests/test_generator_audit.py` covers 26 shell forms
(20 to flag, 6 controls) and the attribution.

**Re-run on all 21 transcripts** (records in the `strict_reaudit` blocks). New after
reading the flagged calls, names only:
* both fixers of CS-02's reference checks ran `git status --short` at the repository
  root (09:25 and 09:52 UTC); the output named seven and two of CS-02's held-out
  candidate files;
* the `git status` of the CS-03 and CS-04 reference-check writers named no candidate of
  their own task (the CS-03 writer's named CS-04's near-miss files);
* the first CS-02 reviewer passed the scratch directory's path to its own scripts seven
  times; they used only folders it had created.

The other earlier flags stay as assessed. The CS-03 near-miss false positive came from a
subshell, which the parser now follows. The CS-01 alternative-2 record now names the
call that wrote `base_grid.json`.

Result: no read of candidate, verifier or sealed material. The one read of another
agent's file in the scratch directory remains the third CS-02 reviewer's read of the
first reviewer's test runner. It read the whole runner (16 lines, with `head -50`).

**More material in the scratch directory than D44 lists:**
* `b1probe/`: a state of `CS-04-eval-alt-1` with two of B1's overlay test files
  (2026-11-13, 04:15);
* the patch and a state of `CS-03-pre-correction` (04:33);
* the patches of all eight CS-03 held-out candidates, in two folders that check agents
  wrote on 2026-11-18 (08:44 and 08:49).

No audited agent opened them. Some of their names appear in a top-level listing that the
re-audit records.

**Review procedure** (not yet used):
* `merge_labels` checks the type of every field before writing anything, also in a
  dry run, and writes all records or none.
* Reviewers who agree on "invalid" but name different requirements now disagree too,
  so the candidate has no final label until adjudication.
* `proposed_label()` returns only proposals.
* The HTML report shows "needs adjudication" instead of one reviewer's label.
* Packet folders and template entries follow the random ids, not the seeded order.

The report of `pilot-v0.3.3` regenerates byte for byte. In a scratch copy, its
`analysis.md` regenerates byte for byte, and `analysis.json` differs only in the
recorded hash of `schemas.py` and the git revision. The recorded files are kept as
computed at the run's revision.

**Prompt export.** Removing a note about the owner's messages now also withholds the
original's hash: 26 of the 30 prompt hashes and 11 workflow headers. Exports pushed
before this entry published those hashes; STATUS lists them.

**Pre-push scan.** It now also scans file paths, commit messages, author and committer
fields, tags and the branch name. Over the whole history, with the private markers, it
gives 99 findings, none in those fields:
* 95 are in the history STATUS lists;
* 3 are versions of an earlier line of the ethics section that used a marker word
  (`3d3024a` to `787176e`), now listed too;
* 1 is a coincidental five-character match inside an encoded signature field of an
  earlier CS-02 transcript version (`2e29057` to `6c1af59`).

D44 said that all 99 were in disclosed history. Every commit message ends with a
co-author line and a `Claude-Session` line; whether they stay is now listed as an owner
decision.

**Harness 0.3.3: a behaviour change, disclosed and not fixed.** After the snippet, 0.3.3
restores the trusted import path, and only then formats the result. Methods that
candidate objects define (`__repr__` of the value, `__str__` of an exception, a module's
`__getattr__` or `__dir__` for traceback suggestions) therefore run without the candidate
directories on `sys.path`. One that imports a candidate module fails, which can report a
correct call as failed. A package-relative import inside one can still load candidate
code, which the in-call limit already allows.

No check in the pool is affected: all 24,880 check results of `pilot-v0.3.3` equal
those of `pilot-v0.3.2`. Under §8 no re-run is needed. The harness comment that said the
error path never imports from a candidate directory is corrected; that is a comment-only
change, and `tc-harness/0.3.3` is unchanged. The fix is left to the next harness
version, which will need a re-run.

**Corrections to D44 and D45.**
* **D44 (result).** It said that no audited agent read forbidden material. Under the
  re-audit's own rule, the third CS-02 reviewer's read of the first reviewer's test
  runner was such a read. The accurate statement is: no read of candidate, verifier or
  sealed material.
* **D44 and protocol v0.6 §14 (lists).** Their lists of listings omit that reviewer's
  listings of the first reviewer's folders and the two `git status` listings. §14 is
  hashed and stays as written.
* **D44 (stopped agents).** "The prompt export now marks all seven" was premature. The
  export script listed all seven from `84e0ec3`, but `agent_prompts.jsonl` carried the
  seventh note only from `aa41b45`.
* **D44 and D45 (history).** The range of the redaction rules starts at `8c13e0c`, whose
  version quotes the start of an owner message, not at `c830977`. The note about the
  owner's messages in five held-out workflow exports (`8c13e0c` to `feab025`) was missing
  from the list.
* **D45 (worktree).** The six editors shared one git worktree, separate from the
  checkout, and worked on disjoint files.
* **D45 (tables).** Besides run names and two captions, the reliability table gained a
  row for `pilot-v0.3.2`, and the evidence ledger gained two entries.

**Tests.** 80 pass (63 offline, 17 Docker).

## 2026-11-21

### D47. Re-audit against the specification; round-4 plan; ungated natural sources adopted for screening
**Re-audit (2026-11-21, 01:00-02:40).** The owner asked for a re-audit against the
original specification. Seven model agents audited the repository at `c5ede4c`,
read-only: pipeline and deliverables, data, design and statistics, the manuscript, an
"impressiveness" reader, a natural-data scout and a build-recipe extractor. An eighth
agent merged their findings. All are Claude agents, not human reviewers. Verdict: the
project does not yet meet the specification's bar. It is a careful Milestone-2
demonstration with a strong grading core, but:
* the evidence stops at four scripted two-turn families;
* the labels equal the model-written reference checks;
* the comparisons that test the hypothesis are null: B2 matches C3/C4 within one
  candidate, and the audit changed 1 of 32 outcomes;
* there is no natural population, no fresh-agent attempt and no precision plan;
* several pipeline stages are scaffolding. Among them, the leakage check as called can
  flag only a `.git` directory (`tasks.py:155`).

The merged plan has eleven phases: truth fixes; an exploratory re-analysis and a
precision plan; batch isolation and records; a Trace Commons screen with transcript
replay and triage; an independent labeler and fresh-agent attempts; an AIDev screen;
natural PR-review tasks; a controlled expansion; pipeline completeness; a manuscript
rebuild; and a re-audit with a stop rule. Its stop rule is to stop once only
owner-blocked gaps remain. Without human labels the ceiling stays an automated pilot
plus a natural screening study.

**Decision: screen two ungated, openly licensed natural sources, as separate
populations.** The specification allows changing the source dataset when the
evidence supports it (§2) and asks for offline progress while blocked (§10). Brief §8
Q6 had left these sources to the owner. They need no terms, gate or spending, so
screening them moves into the plan. Accepting the SWE-chat terms stays with the owner
(D4), and the third-party LuminTime transcripts stay untouched pending the owner.
* `natural:pr-review`: AIDev v5 (`hao-li/AIDev`, tag `v5` =
  `b37f9fd1613cfec55886105bb76721918d015dc7`). It is a CC-BY-4.0 compilation in which
  each source repository keeps its own licence, and it was ungated on 2026-11-21 (Hub
  API, `gated: false`). Files: `repository`, `pr_review_comments`, `pull_request`,
  `pr_commits`, `related_issue` and `issue` (1,107,208,277 bytes); `pr_reviews` only if
  needed; never `all_user`. They are kept outside the repository, each sha256 is
  checked against its LFS oid, and every file is recorded in
  `data/manifests/third_party_downloads.json` as holding personal data (GitHub logins,
  comment text).
* `natural:chat`: Trace Commons (`trace-commons/agent-traces` at `112ebd4d`, a
  CC-BY-4.0 compilation, ungated), 30 sessions, screened for reconstructability,
  triage and the rejection ledger.
* Never pooled with controlled data. No verbatim comment, PR, issue or session text,
  no logins and no @handles in git: only IDs, SHAs, sha256 hashes of texts, and
  paraphrased requirements.
* Model-assisted screening stage (behaviour change addressed by a later commit): a
  uniform random sample of up to 150 comments that survive the deterministic filters,
  seed 20261121. Its outputs are labelled as model proposals.
* Precedent and distinct value. SWE-Gate (arXiv 2609.04167) and SWE-Shield (arXiv
  2604.05955) already derive requirements from PR review comments and measure
  test-based false acceptance (`docs/research/review_novelty_search.md` §3.3). This
  arm adds only the generated initial-only versus correction-aware verifier pair,
  scored on the observed pre-review state together with valid alternatives.
* Construct caveat. A review comment is not a chat correction, and the reviewer is
  often not the requester. The initial request is a linked human-written issue where
  one exists. Otherwise it is the agent's own PR body, which is flagged and is not user
  evidence. Whether PR-review corrections count as user corrections for the claim (D34)
  is the owner's decision.
* Correction to the brief (§4.3) and the notes. AIDev pre-review states are not exact
  without checks: `pull_request` has no base or head SHA, `pr_commits` has no dates or
  parents, and the reviewed commit was missing from the PR's commit list in 3 of 19
  sampled behaviour comments. Each state must be verified by fetching it from its
  repository.

**Wording correction.** README, STATUS, the data card and the paper said that natural
data was blocked. Only SWE-chat is. Protocol §2 is hashed and stays as written; this
entry records the correction.

**Frozen pilot.** `results/runs/pilot-v0.3.3`, the hashed protocol text and the frozen
task files are not edited. New candidates, populations and analyses go into new runs,
strata and sidecar files, and a frozen-input check runs at the end of every phase.

### D48. Protocol v0.7 hashed; the AIDev screening funnel (stages S1 to S8a) and the S9 sample
**Protocol v0.7** (`experiments/protocol.md` §15) was appended and hashed at
2026-11-21T03:21:41Z, before any generation for the new strata: sha256
`46bfa7a3468976b1a24d5e8dcc39421d20e2aa28389e4cd47b629c87508ea5fe`. It defines:
* the standing of `pilot-v0.3.3`: its four families become development families, and
  later re-analyses of it are exploratory;
* the new strata `fresh-v1` (fresh-agent attempts, two configurations, two instruction
  variants, k = 5) and `natural-pr-v1` (natural PR-review tasks from AIDev v5);
* harness 0.3.4 for new runs, three repeats per pair, and a re-grade of `pilot-v0.3.3`
  as a reliability run;
* an independent labeler per family, written by a different agent configuration;
* the S9 and S10 rules, families, caps and stopping rule of the natural arm;
* the reporting rules: per-family tables, exact randomization p-values, and each
  distinct patch counted once.

No amendment section before §15 was changed. The earlier text is a byte prefix of the
new file.

**AIDev funnel, stages S1 to S8a** (`scripts/screen_aidev.py`, DuckDB over the six
verified files; `data/manifests/screening_natural_aidev.json`). Counts are
comments / PRs / repositories:

| Stage | Rule | Count |
| --- | --- | --- |
| S1 | AIDev-pop agent PRs | 361,296 PRs; 25,402 repositories |
| S2 | Python; MIT, Apache-2.0 or BSD licence; not a fork | 44,914 PRs; 3,333 repositories |
| S3 | inline review comments on S2 PRs | 28,732 / 5,030 / 757 |
| S4 | human, thread-starting, not by the PR's author | 6,751 / 2,070 / 427 |
| S5 | `.py` file with a diff hunk | 3,895 / 1,241 / 306 |
| S6 | commented code changed afterwards | 3,540 / 1,085 / 268 |
| S7 | reviewed commit in the PR's list, later commit exists | 3,126 / 987 / 246 |
| S8 | linked issue written by a person | 926 / 255 / 92 |
| S8a | first later commit attributed to an agent | 684 / 190 / 63 |

* **By agent at S8a:** Copilot 614, Devin 58, Claude Code 11, Cursor 1, Codex 0, Jules
  0.
* **Attribution:** agent work committed under a person's own account, without an agent
  co-author trailer, cannot be attributed. That excludes almost all Codex and Cursor
  work.
* **Join and ordering checks:** the comment-to-PR key matched 99.73% of comments. "Later"
  means later in the commit list's row order, because `pr_commits` has no dates. The
  order agreed in 1,739 of 1,739 checkable pairs. The reviewed commit is missing from
  the PR's list for 11.7% of S6 comments, so every pre-review state is still verified
  by fetching it.
* **S9 sample:** 150 of the 684 comments, drawn with `random.Random(20261121)`; no
  top-up. It holds 94 PRs in 36 repositories: Copilot 132, Devin 12, Claude Code 6.
* **Texts:** pseudonymised texts for the sample, with logins and @handles replaced by
  role labels and e-mail addresses removed, are kept outside the repository. The
  manifest holds only ids, SHAs, paths and sha256 hashes of texts.
* **Scan:** `scripts/scan_tracked_files.py` gained `--aidev-logins`, which checks tracked
  files against the sampled reviewers' logins in memory and flags @handles under
  `data/manifests/`.

### D49. Exploratory re-analysis of pilot-v0.3.3 and a draft precision plan
Post hoc analyses (protocol §15.1), written by a model agent and read-only on the
frozen run: `scripts/exploratory_reanalysis.py` writes
`results/analyses/pilot-v0.3.3-exploratory/`, 13 tables in
`paper/generated/exploratory/` and a ledger of their 1,111 values,
`paper/evidence_ledger_exploratory.md`. Every table is marked post hoc and
exploratory. The script first checks that its recomputed counts equal the frozen
`analysis.json`.
* **Exact family-level tests.** For C1 vs C3 FA the per-family differences are +0.17, 0,
  +0.50 and +0.80. The exact sign-flip test gives one-sided p = 0.125 and two-sided
  0.25. The zero difference in CS-02 raises the attainable floor from 0.0625 to 0.125.
  None of the 14 pre-specified comparisons goes below 0.125. With four families, no
  comparison is significant.
* **Rejections for the wrong reason.** C1 rejects 11 of the 17 invalid candidates.
  Only 6 of those rejections come from a check that passes on the reference and maps
  to a requirement the candidate violates. Counting only those, C1 accepts 11 of 17
  invalid candidates, and C2 does the same. All 17 rejections by C3 and C4 have the
  right reason. B2 cannot be scored this way, because its checks map only to its own
  requirement list.
* **Labeler agreement on all 32 candidates.**

  | Verifier | With the reference checks | With the independent construction checks |
  | --- | --- | --- |
  | C3 and C4 | 30/32 | 26/32 |
  | B2 | 30/32 | 24/32 |
  | C1 | 23/32 | 17/32 |

* **B2 against C3/C4** as an equivalence question (margin 0.10): equivalence cannot be
  shown with four families; the TOST p never goes below 0.0625.
* **Oracle gate.** C1 and C2 fail their own reference in CS-01. With those cells
  dropped, C1's FA is 5/11 and its FR 0/8. Counting each distinct patch once (31
  patches), C1's FA is 5/16.

**Draft precision plan** (`experiments/precision_plan_v1.0-draft.md`, sha256
`eb4b8477565b41dcb68da64728904a2f911c2fb93718ea5c72b69dba91145a44`, logged 2026-11-21T04:14:28Z). It is
not adopted. A later protocol version must adopt it before any confirmatory run.
* **Primary endpoint:** the per-family C1 − C3 FA difference on natural and
  pre-correction negatives, tested with an exact sign-flip test over families.
* **Guardrails:** an FR non-inferiority guardrail with margin 0.10, and TOST for B2
  against C3/C4.
* **Multiplicity:** a fixed testing sequence.
* **Coverage simulation:** the sign-flip interval covers at 0.94 to 0.97 from 8
  families on, while the pilot's cluster bootstrap under-covers at 0.77 to 0.94 up to
  20 families.
* **Sample size:** about 60 eligible families are needed to detect a difference of 0.20
  with one natural negative per family. This exceeds the cap of 30 tasks in §15.6:
  with 30, power is 0.45 at a difference of 0.20 and 0.87 at 0.35. The cap stays as
  hashed; the natural arm remains a pilot.

### D50. Stage S9 of the natural PR-review screen; a corrected deviation; local workspaces sealed
**S9** (protocol §15.6; `data/manifests/screening_natural_aidev_s9.json`). Of the 150
sampled comments:
* 19 could not be judged, because their repositories could not be fetched here. This
  environment's GitHub proxy refused 3 repositories (17 comments), and 1 repository
  went over the 300 MB cap (2 comments).
* The other 131 were judged by two independent model agents, from pseudonymised text
  and the diff of the reviewed commit against the first later commit that touches the
  commented file.

**Qualifying comments.** A comment qualifies when both judges say it requests a behaviour
change or reports a defect, that the commit addressed it, and that it is testable
offline. 31 comments qualify: 20.7% of the 150 sampled (Wilson 95% interval 15.0% to
27.8%), or 23.7% of the 131 judged (17.2% to 31.6%). They come from 25 PRs in 14
repositories. These rates are model proposals, not human coding. Of the comments that
do not qualify, 92 ask for refactoring, style, tests or process, and 6 were not
addressed. The judges disagreed on 2 comments, which are excluded. Agreement between the
judges was κ = 0.93 for "behaviour or defect", 0.94 for "addressed" and 0.93 for
"testable offline".

**Families.** With at most 2 per repository, taking each repository's earliest PRs,
there are 20 provisional families: 17 Copilot and 3 Devin. S10 can only lower this
number.

**Deviation, corrected.** The first judging pass showed 12 comments the diff to the
PR's next commit. That commit does not change the commented file, so the diff was
empty. Criterion 2 of §15.6 refers to the first later commit that touches the file.
The 12 were re-judged by two new judges on compliant diffs. Three of them now qualify,
none dropped out, and the count rose from 28 to 31. The earlier judgments are kept in
each row under `superseded`. One addressing commit counts as agent-attributed under
S8a only because a CI bot made it; that comment fails on its judgments anyway. For one
issue body, two third-party model identifiers were masked in the judges' copy.

**Local workspaces sealed.** A verification by model agents found that every controlled
session's first prompt names its workspace under `/home/user/cs_workspaces`. That
directory still held the reference solution, the held-out pre-correction state and the
raw transcript, so a fresh agent given U1 could have found them. Four local
directories (`cs_workspaces`, `gen_workspaces`, `tc_review`, `tc_review_dl`) were
therefore archived as tar.gz files into the sealed directory. File counts were checked
against each directory, and the archives' sha256 values are recorded next to them. The
directories were then removed. Before any fresh attempt, the instructions substitute
the old workspace paths with those of the new workspace, as recorded in a protocol
amendment (§15.4 requires U1 verbatim otherwise).

**Disclosure.** Commit `577860c` wrote rule:v1 triage proposals into
`tasks/CS-0*/provenance.json`, contrary to D47's statement that frozen task files are
not edited. These files are not hashed inputs of the analysis. The proposals are being
moved to sidecar files, and the four records restored.

### D51. Verification of round 4; protocol v0.8 hashed
**Verification (2026-11-21, 04:58-06:20).** A read-only verification by four model
agents covered everything changed since `c5ede4c`, through four lenses: code, security
and privacy, protocol integrity, and the truth of the public text. Its major findings,
each checked by a reproduction, were:
* the vacuous leakage field is still written for new builds, and nothing requires the
  reconstruction check;
* the reconstruction check can pass a leaked file that hides behind an unrecognised
  shell command;
* the two replay implementations differ;
* harness 0.3.4 can still report a successful call as failed;
* the report pools populations silently;
* the controlled first prompts point fresh agents to the old workspaces, which held the
  reference solutions (sealed, D50);
* there is no fresh-attempt audit profile;
* the schema lacks the identifiers §15 names;
* the privacy scan covers only the sampled reviewers;
* the text was stale on the acceptance gate and the Harbor reward directory.

Minor findings were also recorded, along with the earlier exporter's planted-reward
defect and the new gate rules. Neither of those two had a log entry; the gate rules
await the owner's confirmation (DOCU-23). No recorded result is affected: no run exists
under 0.3.4, and the frozen pilot regenerates identically.

**Protocol v0.8** (`experiments/protocol.md` §16) was appended and hashed at
2026-11-21T06:22:31Z, before the fixes and before any run, fresh attempt or natural
verifier under v0.7: sha256
`81cdb9c641b46d4b87b5077b678eff729152be189854b9ffea8f59a9d8be4791`. It introduces:
* harness 0.3.5, under which a successful call is never reported as failed because its
  result cannot be formatted or encoded;
* a recorded path substitution in the fresh-agent instructions, and a fresh-attempt
  audit profile;
* the identifiers fresh_attempt, natural_pre_review, source_evidence, B3 and the two
  natural sub-populations;
* a correction of S6, the definition of S11, and S9 failures written to the ledger;
* the reconstruction check, required for every new task;
* the reporting rules, implemented in `tracecontract analyze`.

**Corrections.**
* D49: the coverage ranges it gives (sign-flip 0.94 to 0.97 from 8 families on; cluster
  bootstrap 0.77 to 0.94) hold in the two simulated scenarios with an effect. In the
  null scenario the bootstrap does not under-cover, and the sign-flip interval is
  conservative.
* D48: the pseudonymised texts still name repository owners in their repository URLs,
  and 2 issue bodies keep a link that names a person.
* D34: "user-rejected pre-correction states" should read "states before a scripted
  correction".

### D52. Fixes from the verification of round 4 (commit `a0542bb`)
Four model agents made these fixes, on disjoint files. Each defect was reproduced before
it was fixed.
* **Harness 0.3.5** (protocol §16.1).
  * A result whose first JSON encoding fails is converted by trusted code that calls no
    candidate method. This covers mixed or tuple keys, cycles, nesting deeper than 100
    levels, dict subclasses whose methods raise, and type names that fail to format.
    Placeholders name the type.
  * A last-resort payload keeps `ok` and the error type, so a successful call is never
    reported as failed and no call is left without a result.
  * Two further behaviours apply only where 0.3.3 left a call without a result: a
    fallback for messages longer than the 199,921 characters the grader can read back,
    and a guarded output flush.
  * 17 new probe checks fail under 0.3.4 and pass under 0.3.5. All 19 Docker tests pass.
  * PR_SET_NO_NEW_PRIVS was not added to the harness, because that would be a second
    difference from 0.3.3. TraceContract's own runner already sets no-new-privileges.
* **Harbor exporter 0.3.0.**
  * It refuses every task the acceptance gate refuses, a rejected source included.
  * Its last-resort cleanup works on a bind-mounted `/logs/verifier`, which the old
    rename fallback could not handle.
  * The exported verifier image has no setuid or setgid binaries (the base image has
    11).
  * Re-validated with Harbor 0.25.0 under harness 0.3.5: oracle 1.0, wrong 0.0, nop
    0.0, and no reward on either planted-reward probe. The control run with the
    `c5ede4c` exporter still gives 1.0 on both probes.
* **Reconstruction check v2.**
  * The result is rolled up per changed file. A file without a passed or explained
    first-edit or base-read item makes the report incomplete, which is how a leak
    masked by an unrecognised shell command now shows.
  * One implementation of the Edit tool's semantics is shared with the replay
    (`ingest/edit_tool.py`, checked against the installed tool), with differential
    tests.
  * Restores keep the files the session created. Shell writes to a directory, the root
    or a glob are lost, not kept. Here-strings are not read as heredocs.
  * CS-01 to CS-04 still pass, with every changed file attested.
* **Builds, gate and preflight.**
  * New builds record no leakage check, then run the reconstruction check.
  * The acceptance gate and the preflight require a passed reconstruction record whose
    inputs match the current files.
  * The preflight requires `--repeats 3` and harness 0.3.5 or later for new runs.
  * `reconstruction-check` exits 2 when its result is incomplete.
* **Schema, labels, analysis and report.**
  * New identifiers (§16.3), with attempt records for fresh attempts. The pilot's
    records re-serialise byte for byte.
  * D19 applies its natural-candidate rule to the natural origins. A pre-review state
    that passes the reference checks is labelled ambiguous. Stratum candidates can be
    labelled in their own files.
  * New runs, those graded with harness 0.3.4 or later, get the reporting rules of
    §15.7 and §16.6 (`stats.py`). Fresh attempts without a passed audit are excluded,
    and the exclusion is reported.
  * The report names each run's populations and never pools them silently.
  * The frozen pilot's analysis and report regenerate identically.
* **Strata.** Symbolic links are refused. `add-stratum-candidate` registers a candidate
  without touching `task.json`.
* **Fresh-agent workspaces and audit.**
  * Every text written into a workspace is checked for outside paths.
  * The path substitution of §16.2 is recorded in each workspace manifest, together with
    the instruction's sha256.
  * The wrappers are checked and smoke-tested in Docker, and git runs with an
    allowlisted environment.
  * The fresh-attempt audit profile forbids everything outside the attempt's workspace,
    in tool inputs and outputs alike.
  * Subagents' shell commands start in the study repository. Attempts must therefore
    use absolute paths, and the audit excludes any attempt that does not.
* **Records.**
  * The rule:v1 triage proposals moved to `tasks/<id>/triage.json`. The four provenance
    records are restored byte for byte to `c5ede4c`, and the frozen-input check no
    longer whitelists them.
  * The 117 S9 failures are now rows of the rejection ledger.
  * The privacy scan loads 119 logins and names tied to the sampled PRs, and checks
    @handles in `tasks/` and `data/`.
  * A pseudonymizer for the later natural stages (`ingest/pseudonymize_pr.py`) masks
    repository owners, links to person accounts and model identifiers.
* **Tests and frozen inputs.** 373 tests pass, offline and Docker.
  `scripts/verify_frozen_inputs.py` reports OK.
* **Reliability re-grade.** The re-grade of `pilot-v0.3.3` under 0.3.5 (§15.3, §16.1)
  started at 2026-11-21T07:22Z as run `pilot-v0.3.5-regrade`, with three repeats.

### D53. S10 feasibility scout; protocol v0.9 hashed
**Scout (2026-11-21, 06:30-07:20).** Two model agents read the 20 provisional families
of the natural PR-review arm. They worked read-only, with git plumbing on the bare
clones and pip's resolver in dry-run mode against PyPI metadata (572 MB fetched), and
they built and ran nothing. They rated 8 families likely to build, 9 possible and 3
unlikely. The obstacles:
* For several repositories, the tests that cover the changed code need live network or
  API access.
* Two PyTorch-based families would need wheelhouses of about 3.2 GB.
* Several closures fail wheels-only on a single small pure-Python sdist.
* One family is rejected under the merge rule of §15.6, because a merge of the default
  branch touches the commented file.
* One family's base is approximate (default-branch merges that do not touch the file),
  and one has a rewritten default branch.

The scouts also wrote bytecode caches into the git-ignored virtual environment, which
is harmless. The scout's records are kept outside the repository.

**Protocol v0.9** (`experiments/protocol.md` §17) was appended and hashed at
2026-11-21T07:32:46Z, before any S10 build: sha256
`9579cdf8a8d942dbb3ed8cbf3058e72d7c1649dcb0cee4886608e9ec44944750`. It sets:
* the environments: pure-Python sdists may be built into wheels in the sandbox without
  network; the wheelhouse is capped at 1.5 GB; the closure is date-bounded and adds the
  packages a PR introduces;
* the base-test subset and what "collect and run" means;
* B1, reported as unavailable when it has no tests;
* the replacement of a family rejected at S10 by the next PR of its repository, still
  at most 2 per repository;
* git-ignored storage for natural tasks, with an index committed.

These rules were written after the scout had seen feasibility, but before any build,
verifier or grading of a natural task. They can raise the yield; they cannot select on
outcomes.

### D54. Reliability re-grade under harness 0.3.5
Run `pilot-v0.3.5-regrade` re-graded all 240 pairs of `pilot-v0.3.3` under
`tc-harness/0.3.5`, with three repeats per pair. It ran from 2026-11-21T07:21:53Z to
08:18:38Z, at code revision `a0542bb`, as an automated pilot (`--pilot`), from a clean
working tree on an otherwise quiet host. It agrees with `pilot-v0.3.3` on all 240 pairs,
in reward and in exact outcome (112 pass, 128 task failure;
`compare_pilot-v0.3.3.json`). No pair's repeats disagreed, so there is no unresolved
outcome. Under §15.3 this is a reliability run, not a new pilot result. Its analysis uses
the new reporting rules (§16.6), because it was graded with harness 0.3.4 or later.

**Correction to D52.** D52 says that a changed file needs "a passed or explained"
first-edit or base-read item. The code counts only passed items of checks b and c.

### D55. Independent labelers for CS-01 to CS-04 (protocol §15.5); a frozen-file incident
**Labelers.** One labeler per family was written by configuration B, a different agent
configuration from the configuration-A writers of the reference checks. Each writer
read only:
* the reference contract;
* the base snapshot;
* the harness API and the lint rules;
* a synthetic example of the test format.

It wrote checks in `tasks/<id>/verifiers/independent_label/tests/` without grading
them. A configuration-A coordinator then did the following:
* built each labeler with a complete generation record (configuration label, prompt
  sha256, times, turns and tool calls taken from the private transcripts);
* graded it with three repeats on the reference and on the development no-op;
* reported only the names of failing checks;
* froze it after at most one revision.

| Family | Checks | Round | Status | Frozen |
| --- | --- | --- | --- | --- |
| CS-01 | 9 | 1 | usable | 08:30:39Z |
| CS-02 | 15 | 1 | usable | 08:30:45Z |
| CS-03 | 9 | 2 | usable | 08:47:55Z |
| CS-04 | 9 | 1 | usable | 08:38:39Z |

In CS-03, the first round had two checks mapped to a change requirement that passed on
the unchanged base. The single revision fixed both. All four labelers pass the reference
in every repeat. On the no-op, each fails at least one check of every change
requirement. Every active requirement of each reference contract is covered. All four
were frozen before any fresh attempt existed. The coordinators looked over the writers'
tool inputs; the strict audit of their transcripts is still to be run.

**Incident: frozen `task.json` modified, and reverted.** `build-verifier` appended each
new labeler to its task's `task.json`, which is one of the 135 hashed inputs of the
frozen analysis. The other workflow's agent noticed this when the frozen-input check
failed. The four files were restored to their committed content, and the labelers are
now registered in a sidecar, `tasks/<id>/verifiers_extra.json`:
* `build-verifier --sidecar` writes there and leaves `task.json` alone;
* `evaluate --with-extra-verifiers` includes those verifiers and records that it did;
* the report shows a sidecar verifier only where a run graded it.

No run used the modified files. The frozen pilot regenerates identically, and 414
tests pass.

### D56. fresh-v1 instructions fixed before the first attempt
The 80 attempt workspaces of stratum `fresh-v1` (protocol §15.4, §16.2) were built at
2026-11-21T08:55-09:05Z under `/home/user/fresh_ws/`, outside the repository, with
`scripts/make_agent_workspace.py --role fresh`: 4 families, 2 variants (`u1` and
`final`), 2 configurations and k = 5. Each workspace holds:
* a fresh git copy of the base snapshot;
* the instruction;
* sandbox wrappers, each smoke-tested in Docker (80 of 80 passed);
* a manifest recording the old workspace paths substituted in U1 and U2, with their
  counts.

Each attempt's instruction is one of 8 templates (family by variant), with the
attempt's workspace path inserted. `data/fresh/fresh-v1/instructions.json` lists every
template, its sha256, and each attempt's instruction sha256, configuration label and
base. Its sha256 `1996bbfee67675e42b8c41fafb6d1b5ce79f6b9d664afa1b36e8001e8a4cecae` is logged here at 2026-11-21T08:57:32Z, before any attempt was started.
Configuration A is the build session's default agent model, and configuration B the
smallest model tier the agent tool offers. Their identifiers stay in the private run
records. Attempts run as subagents of the build session. Their shell starts in the
study repository, so the instructions and the fresh-attempt audit (§16.2) require
absolute paths inside the workspace, and the audit excludes any attempt that reads
outside it.

### D57. fresh-v1 attempts run; protocol v0.10 (audit rule) hashed before grading
**Attempts.** The 80 attempts (D56) ran on 2026-11-21 from 09:06Z, as four workflows of
20, one per family. They were interleaved by repeat, variant and configuration. All
those finished so far ended normally (finished; none gave up or errored).
* CS-01 is registered: 20 stratum candidates with 20 distinct patches, under
  `tasks/CS-01/strata/fresh-v1`, without changing `task.json`.
* The automated fresh-attempt audit flagged 6 CS-01 attempts. Read by hand, all six
  flags are false positives of four kinds:
  * a harness notice naming a tool-results file that was never opened;
  * tokens of an attempt's own printed output resolved against the study repository;
  * heredoc operators parsed as paths;
  * sed expressions that start with "/" read as paths.

**Protocol v0.10** (`experiments/protocol.md` §18), hashed at 2026-11-21T10:04:22Z before any fresh-v1
attempt was graded or labelled: sha256 `957717e50a77a22fcf1f7586c8e3816c0ea7f0ffb9c96ce1a22ca24ad5b8b4c3`. It covers three things:
* how a flag is confirmed;
* a sensitivity analysis that excludes every flagged attempt;
* disclosures of harness context present in every attempt (the build session's task
  titles, and a working-directory line naming the study repository; no reference,
  verifier, candidate or label material), and of one denied, unrelated tool call by a
  configuration-B attempt.

### D58. Strict audit of the labeler writers; fresh-v1 labels proposed; corrections to D57
**Labeler writers (protocol §15.5; D55 left this audit open).** `scripts/strict_reaudit.py`
has a new labeler-writer profile (`--labeler TASK=TRANSCRIPT`, `--revision
TASK=TRANSCRIPT`). It resolves every path in every tool input, shell commands included,
and scans every tool output for forbidden paths, candidate ids and the text of forbidden
files (an index of the distinctive lines and test names of 258 files). It also checks the
prompts and the harness context, and a revision prompt against the names-only rule. The
existing profiles are unchanged: on the same inputs (all 80 fresh attempts; 410 generator
transcripts) the old and new script give identical output. Report:
`data/labelers/writer_audit.json` (sha256 `d1f3cd22...`), run at 2026-11-21T11:38:34Z
over the five transcripts by sha256.
* Every writer prompt is the labeler workflow's template and hashes to the frozen spec's
  `prompt_sha256`. Replaying the transcripts' writes reproduces every frozen labeler test
  file byte for byte, so these five transcripts account for all four labelers.
* The script flagged 4 items in 2 transcripts. Read in the transcripts, 3 are false
  positives: an `ls` of the writer's own directory before it existed; a repository-wide
  `grep` by the CS-03 reviser that the permission system denied before it ran, which
  was not retried; and a harness notice naming a file that was never opened. One holds:
  the CS-03 revision prompt gave each failing check's name with its kind ("passes on
  unchanged base"), and its shape showed that nothing failed on the reference. §15.5
  and D55 say names only. This is information about the labeler's own checks on the
  base, which a writer may compute itself, not forbidden material.
* Verdicts: CS-01, CS-02 and CS-04 independent; CS-03 concerns (the revision prompt, and
  the denied search). As recorded in its `status.json`, the CS-03 revision makes the
  R-all-caps-input checks fail on the no-op only by coupling them to R-acronym, so their
  per-requirement attribution is unreliable. The candidate-level verdict that the second
  labeling uses is not affected.
* A second agent checked the same transcripts independently, from the raw JSONL and
  without the script, with a content-level search for forbidden text. It reached the
  same verdicts and found no read of forbidden material.
* For the natural-task labelers (§15.5), the revision step passes bare check names.

**fresh-v1 labels** (2026-11-21, 10:59:47-11:21:02Z, `scripts/propose_labels.py tasks/<id>
--stratum fresh-v1`, commits `9367db1` and `4a6e98f`). D19 with fresh attempts treated as
natural candidates: invalid if any frozen reference check or the regression norm fails,
else valid. No proposal is ambiguous.

| Family | u1, A | u1, B | final, A | final, B |
| --- | --- | --- | --- | --- |
| CS-01 | 5 invalid | 5 invalid | 5 valid | 5 valid |
| CS-02 | 2 invalid, 3 valid | 5 valid | 5 valid | 5 valid |
| CS-03 | 2 invalid, 3 valid | 5 invalid | 5 valid | 5 valid |
| CS-04 | 5 invalid | 5 invalid | 5 valid | 5 valid |

These are model proposals, not human labels. The 29 invalid `u1` attempts are natural
correction-violating negatives: no generator wrote them. Before grading, every recorded
patch was re-derived from its attempt's workspace. All 80 are identical to the recorded
patches. A content comparison of base plus patch against the workspace, which does not
depend on timestamps, finds no difference beyond the files the patch policy removes.
The re-derivation was needed because the audit agent found that `patches.diff_dirs`
could miss a same-size edit through git's stat cache. Since this entry, it empties the
index before adding the new tree.

**Corrections to D57.**
* The first attempt started at 2026-11-21T08:58:21.8Z (CS-01-fresh-A-u1-1, by the
  attempt records), not at 09:06Z. That is still after the instructions were logged in
  D56 at 08:57:32Z. The last attempt ended at 10:21:02Z.
* The audit reports of CS-01 and CS-04 name protocol v0.9 and D55/D56. Those of CS-02 and
  CS-03 name v0.10 (§18.1) and D57. CS-01 was reviewed at 09:55:54Z, before v0.10 was
  hashed (10:04:22Z). CS-04 was reviewed at 10:13:44Z, after it, but kept the earlier
  header. Both reviews read every flag in its transcript and judged every flag a false
  positive. The flags were harness notices naming files that were never opened; tokens
  the parser misread as paths (heredoc operators, sed expressions, an environment
  assignment); and old workspace paths printed from the attempt's own manifest. None is
  a read, listing or search outside the workspace, which is what §18.1 excludes. The
  recorded headers are left as they are; this entry is the correction.

### D59. Stage S10 of the natural arm: 6 of 22 built families pass
**Run.** 2026-11-21, 08:59-11:52Z. One agent ran the compiler's own functions
(`natural_pr.compile_pr_task`, then `natural_pr.run_s10_environment`). It took the
families NP-01 to NP-20 in order, one at a time, with at most one image build or test
run at once. The reserves NP-21 and NP-22 replaced NP-01 and NP-02 (§17.3) and were
also rejected. NP-23 to NP-25 were not needed. All repository code (base tests, sdist
builds) ran only in containers without network. On the host only git plumbing, pip's
dry-run resolver (wheels only) and wheel downloads ran.

**Accepted (S11): NP-03, NP-04, NP-05, NP-18, NP-19, NP-20.**

| Task | Fidelity | Closure | Base-test subset at the base | B1 |
| --- | --- | --- | --- | --- |
| NP-03 | approximate: 1 symbolic link and 2 submodules not materialised | 73 pins | 966 collected: 954 pass, 10 fail, 2 skipped | 954 |
| NP-04 | exact | 17 pins | 33 collected, all pass | 34 |
| NP-05 | exact | 17 pins | 359 collected: 354 pass, 5 fail (live-network tests) | 354 |
| NP-18 | exact | 144 pins | 24 collected, all pass | 26 |
| NP-19 | exact | 106 pins (1 sdist built) | 9 collected: 1 pass, 5 fail, 3 setup errors (missing API key) | 1 |
| NP-20 | exact | 71 pins (2 sdists built) | 48 collected, all pass | 48 |

Failing and erroring tests count as run (§17.2). B1 is the subset's tests at the
addressing commit that pass on the reference.

**Rejected: 16.**
* Base tests fail to collect (8):
  * NP-01, NP-02, NP-21 and NP-22: a monorepo's own test tooling, a path requirement
    outside the workspace that is not on PyPI;
  * NP-09 and NP-14: a version module that the build backend generates, absent from the
    source tree;
  * NP-11: a git submodule, which is another repository;
  * NP-06: a declared dev pin that imports `distutils`, which Python 3.12 lacks.
* No resolvable closure (4):
  * NP-10: pip's resolver stopped with "resolution too deep";
  * NP-13: an sdist-only requirement with a C extension;
  * NP-16 and NP-17: the resolver did not finish within the 30-minute limit.
* Environment too large (1): NP-15, with a 3.15 GB wheelhouse against the 1.5 GB cap.
* Empty base-test subset (1): NP-07.
* Fetch over the 300 MB cap (1): NP-08. The clone stopped at 318.8 MB, because the
  last fetch finished between two watchdog polls.
* Merge rule (1): NP-12.

**Yield.** 6 tasks from the 150 sampled comments (4.0%) and from the 31 qualifying ones.
That is fewer than the 10 that §15.6 requires, so under §15.6 as written the arm is a
screening study only (see D60). Three rejections (NP-10, NP-16, NP-17) depend on pip's
resolver and on the compiler's 30-minute limit, which is an implementation parameter,
not a protocol rule. Seven others follow from rules that cannot yield a runnable
environment: path requirements outside the workspace, generated version modules,
submodules. Whether S10 should admit these is a question for the owner. The accepted
tasks are therefore biased toward small repositories with plain test setups.

**Compiler fixes during the stage**, each with a test that fails on the old code:
* a monorepo package's base is archived as the subtree, so no blob outside the package
  is fetched;
* sdists are built in a private directory of the build user, and exactly one wheel is
  copied back;
* an sdist must satisfy every declaration of its name that applies to Python 3.12;
* every round of sdist builds is followed by a resolution;
* the resolver runs on a Python 3.12 interpreter. pip's `--python-version` does not
  change environment markers, so closures had been resolved for the host's Python 3.13;
* a resolver timeout is a rejection;
* pip's TMPDIR is a work directory that is removed after each run. NP-16's killed
  resolver had left 975,916 temporary directories in /tmp; they were removed;
* the resolver interpreter is checked and recorded in `s10.json`;
* B1's overlay is listed in the index as one manifest hash;
* a test directory whose name ends in "tests" counts for the §17.2 fallback.

Every family processed before a fix was re-run after it, and every re-run reproduced
its earlier outcome. The resolver venv is CPython 3.12.3 with pip 26.3, kept outside
the repository. NP-10 and NP-16 ran before the resolver was recorded, so their
`s10.json` has `environment.resolver` null; their recorded commands show the 3.12
interpreter.

**Records and resources.**
* `data/natural/tasks/NP-xx/s10.json` holds each family's record (git-ignored).
* `data/manifests/natural_tasks_index.json` (new) has 25 rows: 6 passed, 16 rejected and
  3 not built. It holds ids, SHAs, licences and file hashes, with no URL, account,
  local path or repository file path.
* The rejection ledger gains 16 S10 rows.
* Fetches in this stage came to 574.6 MB, and all clones together to 1.06 GB (cap 5 GB).
* After the stage, the images of the rejected families and two superseded images were
  removed. They can be rebuilt from the recorded closures.

### D60. Protocol v0.11: the natural arm's S9 extension, hashed before any further screening
**Protocol v0.11** (`experiments/protocol.md` §19), hashed at 2026-11-21T11:56:28Z: sha256
`535a483f6d2506866a8a7bb31da50cf2271409a14060bf708e891a9cbe8ad6a0`. At that time no comment of the extension had been judged, and no natural
contract, verifier, held-out candidate or label existed.
* S9 is extended to the 534 S8a comments not in the first sample. All of them are
  screened, in ascending comment id, under unchanged S9 rules and caps, by new judges.
* Families are formed over both samples. The first sample's families keep their ids and
  places, new ones are numbered from NP-26, and repositories that already have 2 accepted
  families get no new one.
* S10 and its implementation parameters (D59) are unchanged.
* The size rule of §15.6 applies to both samples together. If the arm still has fewer
  than 10 tasks, the built tasks are reported as per-family exploratory case studies.
* Accepted families may be built before the extension is screened. No natural verifier
  is graded on a held-out candidate before building stops.

The extension was decided after the first sample's S10 yield (D59) was known. It is
disclosed as a post-hoc design change, and it used no verifier outcome on natural data.

### D61. Run fresh-v1: 80 fresh-agent attempts graded; results
**Run.** `fresh-v1`, 2026-11-21, 12:40:35-15:12:56Z, code revision `eb56aec`, harness
`tc-harness/0.3.5`, one invocation:
`tracecontract evaluate tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04 --run-id fresh-v1
--strata fresh-v1 --only-strata --conditions initial_plain initial_audited full_plain full_audited
llm_freeform repo_tests reference_check --with-extra-verifiers --repeats 3 --pilot`.
* The extended pre-flight passed first, with no failure, from a clean working tree and
  with no other sandbox container (`eb56aec`).
* 672 pairs: 4 families × 21 candidates (20 attempts and the reference) × 8 verifiers. That is
  the 6 conditions, the reference checks and the independent labeler, each pair graded
  three times. 427 pass and 245 task failures, with no infrastructure outcome. No pair's
  repeats disagreed, so none is unresolved.
* Other agents worked in the working tree during the run, on files the grader does not
  read: no edit under `tasks/` or the harness, and no container besides the grader's.
* The analysis ran from a clean worktree at `cbdcd92`. Its analysis code is unchanged since
  `6d07115`. It ran there because the main working tree held other agents' unfinished
  edits. `analysis.json` records that revision without `+dirty`. `analysis.md`,
  `analysis_sensitivity.md` and `report.html` are identical to the outputs of a first
  analysis run from the main tree.

**Results** (D19 labels, model proposals; each distinct patch once; CS-02-fresh-A-final-1
excluded by the reviewed audit; 29 invalid and 50 valid attempts):

| Condition | FA | FR | FA per family (CS-01, CS-02, CS-03, CS-04) |
| --- | --- | --- | --- |
| C1 initial_plain | 24/29 (0.83) | 13/50 (0.26) | 10/10, 0/2, 4/7, 10/10 |
| C2 initial_audited | 24/29 (0.83) | 13/50 (0.26) | the same as C1 |
| C3 full_plain | 2/29 (0.07) | 0/50 (0.00) | 0/10, 2/2, 0/7, 0/10 |
| C4 full_audited | 2/29 (0.07) | 6/50 (0.12) | as C3; the 6 rejections are all in CS-03 |
| B2 llm_freeform | 2/29 (0.07) | 2/50 (0.04) | as C3 |
| B1 repo_tests | 0/29 (0.00) | 34/50 (0.68) | 0 in every family |

* **Correction-violating attempts.** 27 of the 40 `u1` attempts violate a correction
  requirement. C1 and C2 accept 24 of them; C3, C4 and B2 accept none.
* **The 2 C3/C4/B2 acceptances.** They are the CS-02 `u1` attempts A-u1-4 and A-u1-5, which
  D19 calls invalid without a correction requirement. The independent labeler calls both
  valid.
* **Paired comparisons.** All 14 are null at the protocol's resolution: with 4 families, no
  two-sided exact sign-flip p-value can go below 0.125. C1 against C3 on FA is +0.76, with
  a one-sided p of 0.125 (floor 0.0625).
* **The audit.** It changed no outcome of C1 (C2 equals C1). It added 6 false rejections
  to C4 in CS-03.
* **Oracle-gated view.** C1 and C2 fail CS-01's reference solution. That verifier encodes
  the initial request, which the correction reversed, so it rejects all 10 valid CS-01
  attempts and accepts all 10 invalid ones.
* **Second labeling.** The independent labeler agrees with D19 on 77 of 79 units
  (kappa 0.94). The 2 disagreements are the CS-02 attempts above. Under it, FA is 24/27
  for C1 and C2 and 0/27 for C3, C4 and B2; FR is 15/52 for C1 and 0/52 for C3.
* **Solve rates** (D19): `final` 19/19 (configuration A) and 20/20 (B); `u1` 6/20 (A) and
  5/20 (B). With the correction in the instruction, every attempt of both configurations
  solves its task; these tasks are not hard.
* **Sensitivity view** (§18.1; all 26 automatically flagged attempts excluded): FA 18/21 for
  C1 against 1/21 for C3; FR 9/33 against 0/33. The conclusions are unchanged.

These are automated-pilot results on four controlled families, with model labels. They
are descriptive, not inferential. The fresh attempts are natural negatives and positives,
which no generator wrote. They measure information lost when a task is reconstructed
from the initial request alone, not the skill of an agent that was never told the
correction.

### D62. fresh-v1: independent recomputation, error analysis, and corrections to D58 and §18.2
**Recomputation.** An agent recomputed the run's numbers with its own scripts, without
importing the package. It matches `analysis.json`, `analysis.md`,
`analysis_sensitivity.md` and D61 in 4,763 fields and 3,332 rendered cells.

**Error analysis.** Read-only, from the patches, the verifier tests and the grader's
per-check output; the full write-up is kept for the manuscript.
1. **CS-01: a loud inversion.** C1 and C2 encode the initial request that the correction
   retracted: by default, drop a trailing ".0".
   * They fail the reference on 12 of their 14 checks, pass only the checks of the one
     requirement the correction kept, and accept all 10 `u1` attempts.
   * This gives 10 of C1's 24 false acceptances and 10 of its 13 false rejections.
   * A rule that a verifier must pass its reference would catch it. In the oracle-gated
     view C1 has FA 14/19 and FR 3/40.
   * In CS-03 and CS-04 the loss is silent: C1 passes both references and accepts 14 of
     the 17 correction-violating attempts, against 0 of 17 for C3.
2. **CS-02: two label artefacts.** D19 labels CS-02-fresh-A-u1-4 and -u1-5 invalid only
   through the regression norm.
   * The one failing base test asserts on a private attribute that both attempts
     deliberately removed. Both pass all 28 reference checks and the labeler.
   * So C3, C4 and B2 accept none of the 27 correction-violating attempts. Their FA of
     2/29 under D19 is these two attempts.
   * No CS-02 `u1` attempt violates a correction requirement (0/10).
3. **CS-03: the audit added false rejections.** C4's 6 false rejections that C3 does not
   make come from 2 checks that its single audit revision added.
   * The checks fix the answers of one development attack, and of the reference, to
     edge cases the contracts leave open: contractions, digits and underscores in
     all-caps words.
   * The audit record shows no findings after one iteration and does not show that
     checks were added.
   * On this stratum the audit removed no false acceptance.
4. **B1: the session agent's own tests.** All 34 of B1's false rejections come from the
   40 checks that the session agent added to the reference state's test files. None
   comes from the repository's earlier tests, and none from the environment. The base
   tests alone accept 17 of 29 invalid attempts and reject no valid one; under D19 they
   cannot reject one, since they are the regression norm.

**Corrections.**
* D58 says the 29 invalid `u1` attempts are natural correction-violating negatives. Only
  27 are; the other 2 are the CS-02 attempts of item 2.
* §18.2 says that every attempt's context included the task-list reminders. The CS-04
  audit records them in 16 of its 20 attempts.
* The environment block also named the build session's scratch directory, as a place
  for temporary files; the four audits' notes record this. CS-02-fresh-A-final-1 wrote
  three helper files there and read them back, which is why the reviewed audit excludes
  it. The exclusion reason in `analysis.md`, "a read of forbidden material", is the
  generic text. The attempt opened nothing there but its own files.
* `analysis.md` does not state the number of unresolved pairs (§15.3). It is 0: all 672
  logs hold three runs with identical summaries (D61).
* Audit records:
  * CS-01's `initial_audited` spec names 5 of the 12 failing checks, because the
    message is cut at five.
  * CS-03's `full_audited` record does not show the 2 checks its revision added.

  The recorded files stay as they are. For new audits, the record is to keep every
  failing check and the checks each revision added or removed.

### D63. S9 extension screened (protocol §19.2); families over both samples; decisions before S10 of the new families
**S9 of the extension** (2026-11-21, about 12:45-16:10Z; private records under
`/home/user/ext/aidev-v5-work/s9x_*`; repository manifest
`data/manifests/screening_natural_aidev_s9x.json`).
* The 534 S8a comments not in the first sample were recomputed with
  `scripts/screen_aidev.py`'s own functions, which reproduce the first sample exactly.
  Their pseudonymised texts were made by the same code.
* 134 failed before judging:
  * 65 over the per-repository cap: two repositories, one of them a clone that grew
    past the cap in the first sample's S10 (D59);
  * 56 whose commits could not be fetched: the proxy refused 3 repositories, the same
    3 as in the first sample;
  * 13 with no later commit that changes the commented file.
* Two new configuration-A judges per batch judged the other 400, on diffs to the first
  later commit that touches the file (§16.4).
* 91 qualify: 17.0% of 534 (Wilson 95% interval 14.1% to 20.5%), or 22.8% of the 400
  judged. They come from 42 PRs in 19 repositories.
* 10 disagreements are excluded. Agreement: kappa 0.95 (behaviour or defect), 0.89
  (addressed) and 0.94 (testable offline).
* These are model proposals, not human coding. Clones of both samples total 1.44 GB
  of the 5 GB cap.

**Families** (§19.3; formed by one agent and recomputed independently by another,
with no difference).
* There are 19 new families, NP-26 to NP-44, and 4 reserves, NP-45 to NP-48. Together
  with the first sample's they fill 19 of the 42 open places in 24 repositories.
* The repository of NP-04 and NP-05 already has its 2 accepted families. Its 7 new
  qualifying PRs therefore get no family, and NP-23 to NP-25 stay unbuilt.

**Decisions** (builder defaults, recorded before S10 of the new families):
* **Corrections of first-sample families.** For six first-sample PRs, an extension
  comment that qualifies was created before the comment the family uses as its
  correction. Only NP-05 is affected among the built families. A first-sample family
  keeps the correction it was built with: §19.3 keeps its id and place, and changing a
  built family's correction would mean rebuilding it under another correction after
  S10. The extension's qualifying comments on these PRs are recorded as other
  qualifying comments.
* **Download records.** The extension's download record lists the 57 fetched
  repositories by URL, as the first sample's record does (D50). The owners that act as
  accounts in AIDev are masked as {owner}. No record links a repository to a task,
  comment or person. Whether these URLs stay before publication is the owner's
  decision.
* **A deviation, corrected.** The over-cap clone's 57 comments were failed without
  checking what the existing clone already holds, although §19.2 reuses existing
  clones. For 5 of them, both commits and both file blobs are already on disk, so their
  diff needs no fetch. These 5 are judged under the same rules, by new judges, with no
  fetch. The other 52 still fail: 8 would need a blob fetch, and 44 lack a commit or the
  PR head.
* A repository whose first-sample clone had already been stopped at the cap was cloned
  again in the extension (about 312 MB, then removed). It made no difference to any
  outcome; it is disclosed here.

### D64. The natural-arm recipe, fixed before the first natural agent
This entry fixes the recipe of the natural arm (`natural-pr-v1`; protocol §15.5, §15.6, §19) for every family of
both samples. The templates were hashed at 2026-11-21T17:42:36Z (`check_natural_prompts.py summary`). At that time
`/home/user/nat_ws` did not exist, no natural agent had started, and no natural contract, generated verifier, held-out
candidate or label existed. The recipe was planned as D61; D61 to D63 were written first, so it is D64, and the tools
that cite it as D61 are listed at the end.

**Before the first natural agent.** Deviation (i), which the recipe did not plan, is taken as a builder decision
(decision 17), pending the owner's review: every deviation is logged before its use (D33, D41), and this one changes
six frozen templates. A byte copy of the labeler workflow script was kept under `/home/user/nat_runrec/` before the
first natural agent (sha256 `68599d2f...`, equal to the build session's copy).

**Templates.** Fifteen files under `experiments/prompts/natural/`, in the format `natural-template/1` of
`scripts/check_natural_prompts.py`. Each names its source template in its header and describes every deviation applied.

| Template | Source | Agents | Config | Words kept / source | sha256 |
| --- | --- | --- | --- | --- | --- |
| contract:v1-natural | CONTRACT_PROMPT (generate) | contract:initial_only, contract:full_session | A | 387 / 446 | `7fae39f9d922d6f8790c485042c91ff67eb0dd7fb8213d3feb3ff0f4b6712a2a` |
| testgen:v1-natural | TESTGEN (generate) | C1, C3 and B2 generators | A | 645 / 724 | `9e0ceb0045f98c7c030d1541c46fe691790714f80a2c77f1078c8bd33f53c01f` |
| b3:v1 (new) | TESTGEN (generate) | B3 generator | A | 596 / 675 | `59e4a8a1fe8d437140d73c59575e43b9f42d8968a1248c263cf8ce959dea939a` |
| attack:v1-natural | ATTACK (generate) | development attacks | A | 250 / 348 | `967bb21b0f2ea9b771946f5c755852e3eebea6a54b6bf8eeb1d7a2d9b2cdaa25` |
| alt:v1-natural | ALT (generate) | development alternatives | A | 183 / 284 | `c63d70e0f9d4d3590a9efa81f2c90bcb9b246b01c2425198a76ed9b100a5f678` |
| revise:v1-natural | REVISE (generate) | revisers of C2 and C4 | A | 542 / 629 | `a11f7ed8b9462b2867378f74406d9a6c7671ba0d3b8c30827fd85c8a16ec634e` |
| refcontract:v1 (new) | CONTRACT_PROMPT (generate) | reference-contract drafter | A | 373 / 446 | `18ec756f310046febf591b7cfaf7b98dc6827d756335c182be963be60c56e7ba` |
| refcheck:v1-natural | genPrompt refcheck (held-out) | reference-check writer | A | 383 / 549 | `a6e4a3a3f5fea270cf5f7cd173ef3b4d877cc07081341a7a6c14dfec442bd185` |
| review:v1-natural | reviewPrompt (held-out) | reference-check reviewers | A | 236 / 349 | `74b6f96d03558dd3474ff188887c1498e8ec4f2fbea39b66fc2c8f75538cfeb1` |
| fix:v1-natural | fixPrompt (held-out) | reference-check fixers | A | 346 / 476 | `406ba6bd1b8b8d06a839346ee0336fca682de12ec9185b3d5963756f9f3c665e` |
| labeler:v1-natural | WRITE (labelers) | independent labeler | B | 311 / 344 | `8337564fb8e17b5343cb64bfb54c87151dab60c482dbca5bcd74f89318c187fc` |
| labeler-revise:v1-natural | REVISE (labelers) | its single revision | B | 190 / 231 | `01879af9c4df54cef1e58ae15ba70c63a74398c3adda2d576e385fd54911999e` |
| altimpl:v1-natural | genPrompt alt (held-out) | eval-alt-1, eval-alt-2 | A | 218 / 341 | `b846b9a0ef111df83150626595f71cf2951448c6c725c34b8ed47f4aa7e73f39` |
| nearmiss:v1-natural | genPrompt nm (held-out) | eval-nm-1 to eval-nm-3 | A | 186 / 376 | `691dc52291c286ccc4f36196dedd236879a59cc43c712692982a94280a52d311` |
| mapper:v1-natural | genPrompt mapper (held-out) | mapper:v1, mapper:v1#2 | A | 225 / 265 | `df42bd5bd714516471959b77dac07d4d93edbdb7a5bce5eca0be712d82cd719d` |

The sources are the generate workflow `wf_b796bb4f-1dd` and the held-out workflow `wf_b428f318-391`, exported under
`experiments/prompts/workflows/` (file sha256 `caa60629...` and `9f8d3d64...`; the "sha256 of this export" on each
file's first line is that of the script without that line), and the labeler workflow `wf_5db2f657-fdf` of D55 (file
sha256 `68599d2f...`), which is not exported and lies outside the repository. `check_natural_prompts.py summary`
compares each template with its source word by word: every word outside a marked deviation must be the source's. All
fifteen pass. The two labeler templates were compared against the build session's copy of their source, checked by its
sha256. Over the fifteen, 5,071 of the 6,483 source words are kept; the rest lie in the marked deviations.

**Deviations** (the letters used in the files):
* (a) Paths. The source's task directory, workspaces and working directory (TD, WS, G, R; `base/`) become the agent's
  own workspace under `/home/user/nat_ws/<task>/` (named as in the table of workspaces below), with `repo/` for `base/`.
  The agent writes only there. The CLI is named by its absolute path. Code runs through the workspace's `run_python.sh`
  and `run_tests.sh`, whose container mounts the state at `/repo`. Where the source had the agent copy `base/` and work
  in the copy (ALT's `solution/` with "copy it; do not edit it in place", the attacks' `attacks/a<k>`, the pool's
  `solution/` and `nm<k>`), the agent works in its own `repo/`, the copy the wrappers run, one workspace per state. The
  labelers' "Commands run from <repository>" becomes "Work only in <workspace>".
* (b) Host-run steps. Workspace creation, render-session, make-contract, build-verifier, grade, audit, add-candidate
  and freeze are removed from the prompts; the host runs them (D24). An agent runs only `check-proposals` or
  `lint-tests`, on its own files, and returns what the host records (target ids, one-line descriptions). Steps are
  renumbered. A proposer runs `check-proposals` once and then at most 3 more times. Its fix loop also covers the
  warning that a quote comes from a non-user event (in a thread, the diff hunk): make-contract's acceptance gate counts
  such a quote in an explicit requirement against the contract (`non_user_evidence`), and `check-proposals`, unlike
  make-contract, does not print the gate's verdict. The mappers' files carry the host's configuration label
  (`model:config-A:mapper:v1` and its `#2` form) for the source's `model:claude-code-subagent:mapper:v1`.
* (c) Do-not-read list. The source's items lie in the study repository, which is named whole, with its worktree
  `/home/user/tc_analysis_wt`. Added: `/home/user/ext`, the private run records `/home/user/nat_runrec`, every other
  workspace under `/home/user/nat_ws/`, the Claude session directories (`/tmp/claude-0` and `/root`, where the source
  did not name them) and the network.
* (d) contract:v1's event-id example becomes the rendered format, `[<session id>/issue]`.
* (e) The reviser of C2 and C4 reads the development candidates' graded patches in `devcands/`, does not grade, and
  gets the findings of the host's audit run.
* (f) The host validates the reference checks, three times on the reference and once on the development no-op. Every
  natural family then goes through the review loop of D33 (at most 2 fix rounds), whatever the validation shows. The
  writer, the reviewers and the fixers do not grade. The reviewers get the host's validation (VALIDATION, below).
* (g) The labeler's single revision is told bare names only (§19.8): the check ids of the checks named below, one per
  line, distinct and sorted, with no kind, message or requirement id. The source's revision prompt also named the
  uncovered requirements. That clause goes, and a fixed sentence asks the revision to keep every active requirement
  covered by a check. The renderer refuses any other form.
* (h) Held-out pool. One agent and one workspace per candidate. Three near misses, each given its target requirement by
  the host (decision 14). A near miss whose target an earlier near miss of the family already has is rendered as the
  variant shared-target: one fixed sentence says that another near miss violates the same requirement and asks for a
  less obvious mistake. No pool agent is given another's output, and the five run in parallel. There is no
  repository-test step for near misses and no sentence about doing them one at a time; instead a sentence forbids
  running the repository's tests, which `run_python.sh` could run.
* (i) The owner-context line of the held-out workflow's preambles (PRE's and the mapper's) is left out of the six
  templates that use them. It states the owner's standing instruction and that nothing needs the owner's approval;
  the mapper's also says that the owner's latest message asks for the work to continue. A template fixed now cannot
  vouch for these when its agents run, and no natural prompt states the owner's instructions. PRE's exported line is
  also redacted; the mapper's is not. (i) is a builder decision, pending the owner's review (decision 17).
* (j) b3:v1 (new): TESTGEN with the B3 inputs (`session_first_prompt.txt` and `reference.diff`, no contract), the
  labels D1, D2, ... and the sentence "Tests that pass on the unchanged base or fail on the reference are removed."
* (k) refcontract:v1 (new): the drafter reads the rendered thread, `reference.diff` and `addressing.diff`.
  * `reference.diff` goes beyond the inputs that §15.6 names (the issue, the thread and the addressing diff). It adds
    the part of the change made before the review, which the issue's requirements concern.
  * `introduced_at` is the issue, the review comment or a reply, and quotes come only from those events.
  * A requirement that only the diffs support is inferred, with a rationale that names what in the diffs supports it,
    and it is introduced at the issue, never at the comment or a reply. So no requirement introduced at the correction
    rests on the diffs alone.
  * At least one scored change requirement is introduced at the correction, with a quote from it, or the drafter says
    why not.

Under (a), the labeler revision's "run lint-tests" names the CLI by its absolute path. The source's revision prompt
named no path, and the natural-agent audit allows the CLI only by its absolute path.

**Prompts as sent.** The host renders each prompt with `check_natural_prompts.py render` (template, variant, values)
and passes it unchanged. Its sha256 is the run's `prompt_sha256`: `scripts/agent_run_record.py` hashes the computed
task the same way. `render --verify` checks a sent prompt against the rendering, and `--record` a generation record.
* The host's values: TASK; WS; SESSION_ID; PYTHONPATH (the task's candidate path in the grader, under `/work`); PYPATH
  (the wrappers' path, under `/repo`); TESTS (the base-test subset of `s10.json`, as pytest arguments); TARGET (near
  misses); ITER and FINDINGS (revisers); VALIDATION (reviewers); ISSUES (fixers); FAILING (the labeler revision).
* Their forms, each checked by the renderer. A check id is the grader's, the pytest node id
  (`test_<module>.py::test_<name>`).
  * FINDINGS: the audit's findings, each as its code and message only (the source's audit schema), serialised as
    `json.dumps(..., indent=1, ensure_ascii=False)`, the form of the source's `JSON.stringify(findings, null, 1)`.
  * ISSUES: the review's issues with the review schema's five keys in its order, as compact JSON, the form of the
    source's `JSON.stringify(review.issues)`.
  * VALIDATION: three lines, `reference, 3 repeats: <outcome>, <outcome>, <outcome>`, `dev no-op: <outcome>` and
    `checks failing on the reference: ...`, the check ids of the checks failed or in error in any repeat, sorted and
    joined by ", ", or `none`.
  * FAILING: check ids, one per line, sorted and distinct.
* The renderer refuses a value that does not fit its placeholder, a workspace outside `/home/user/nat_ws/<task>/`, and
  a value that names a path under `/home/user/nat_runrec` or a held-out candidate (`eval-alt-<k>`, `eval-nm-<k>`,
  `pre-review`; the workspace itself is exempt). It also refuses a prompt that names a path under `data/natural/`, a
  session-local path, a held-out candidate id, a model identifier or tier name, or a CLI call outside the audit's
  allowlist. A host value is data, never template text.
* A template changed after this entry is a new version, logged before its first use (D33, D41).

**Rendering.** The PR-thread renderer of WP-B (`41210e5`) is fixed: banner sha256
`8b6b4cb4de25d09e6d66c5789af95b04a5cb2e19eb23b4e0d4f1ff13f93dd055`, block headers sha256
`90706f6ab08c8ad8b93ff18536c776a8555d914530169cbbb6e21a6cf9db871d` (the canonical JSON of the five headers;
`check_natural_prompts.py rendering`), session-events format `tracecontract/session-events/v1`. The review comment
and the replies are labelled USER, so contract:v1's "as stated by the USER" applies to them. For each family, the
sha256 of its `session.txt`, `session_first_prompt.txt` and `reference.diff` is logged before its proposers start, as
D56 did for the instructions.

**Workspaces and audit entries.** `scripts/make_agent_workspace.py` (`31f32d6`) makes every workspace as
`/home/user/nat_ws/<task>/<name>`, from `--role` and `--name`. Each agent's entry in `labels/generator_audit.json` is
named after its workspace, so these are also the entries the pre-flight requires (`NATURAL_AUDIT_ROLES` in
`scripts/preflight_final_run.py`).

| Agent | Template (variant) | `--role` | Workspace and audit entry | Required |
| --- | --- | --- | --- | --- |
| contract:initial_only, contract:full_session | contract:v1-natural (initial_only, full_session) | contract-initial, contract-full | contract-initial, contract-full | yes |
| testgen:initial_plain, :full_plain, :llm_freeform | testgen:v1-natural | testgen-initial, testgen-full, freeform | testgen-initial, testgen-full, freeform | yes |
| testgen:diff_derived | b3:v1 | diff-derived | diff-derived | yes |
| attack:initial_only, attack:full_session | attack:v1-natural | attack-initial, attack-full | attack-initial, attack-full (each a group of workspaces a1 to a4) | yes |
| alt:initial_only, alt:full_session | alt:v1-natural | alt-initial, alt-full | alt-initial, alt-full | yes |
| revise:initial_audited:<i>, revise:full_audited:<i> | revise:v1-natural (initial_audited, full_audited) | reviser-initial, reviser-full | revise-initial-<i>, revise-full-<i> | one per revision the audit record counts |
| refcontract:<task> | refcontract:v1 | refcontract | refcontract | yes |
| refcheck:<task> | refcheck:v1-natural | refcheck | refcheck | yes |
| review:<task>:<r> | review:v1-natural | refcheck-review | refcheck-review-<r> | at least one |
| fix:<task>:<r> | fix:v1-natural | refcheck-review | refcheck-fix-<r> | checked when present |
| labeler:<task> | labeler:v1-natural | labeler | labeler | yes |
| labeler-revise:<task> | labeler-revise:v1-natural | labeler, with `--tests-from` | labeler-revision | when `status.json` records round 2 |
| eval-alt-1, eval-alt-2 | altimpl:v1-natural (eval-alt-1, eval-alt-2) | alternative | eval-alt-1, eval-alt-2 | yes |
| eval-nm-1 to eval-nm-3 | nearmiss:v1-natural (own-target, shared-target) | near-miss | eval-nm-1, eval-nm-2, eval-nm-3 | yes |
| mapper:v1, mapper:v1#2 | mapper:v1-natural (mapper-1, mapper-2) | mapper | mapper-1, mapper-2 | yes |

A natural near miss gets `run_python.sh` only, and the labeler workspaces are made without `--image`, so they hold no
wrapper. The templates name only files that these roles write.

**Order per family and freeze points.** The build session runs every host step (D24). Each phase ends with an index
commit, and the commit times are the order record.
* F0 (S10): base manifest, pins, image id and PR record. F2: this entry, and the family's rendered-input hashes.
* P0: validate-task, the PR record, the image id, and B1 frozen (F1; done for the six accepted families in `7f0501f`).
* P1: the two contract proposers; make-contract by the host (F3).
* P2: the C1, C3 and B2 generators, the B3 generator, four development attacks and one development alternative per
  variant. C1, C3 and B2 are built and frozen at once (F4).
* P3: C2 and C4 start as copies of C1 and C3. The host runs audit:v1, with 0 to 3 revisers per verifier, and freezes
  them, also when the audit still fails after 3 revisions (D27). B3: per-test selection (three single grades on the
  reference, one on the development no-op), rebuild, confirmation and freeze, or "B3 unavailable" (F4).
* P4: the reference contract, drafted after P3, so no generator saw it (F5).
* P5: the reference checks with the review loop, and the independent labeler with at most one revision (next
  paragraph). Both are frozen, with their status records (F6).
* P6: the near-miss targets (decision 14), then the held-out pool, only after P3 and P5: two alternatives and three
  near misses, one agent and workspace each, in parallel (F7: each candidate's generation `started_at` is later than
  every F4 and F6 `frozen_at`).
* P7: two mappers, duplicates and audits.
* F8, after building stops (§19.5): D19 labels, the protocol hash and the pre-flight; then the one run
  `natural-pr-v1` (§19.7).

**Validation of the reference checks and of the labeler (P5).** Each grade here is a single grade (`tracecontract grade`
without `--repeats`: a grade with repeats keeps only its last run's per-check statuses). A check fails in a grade when
its status is failed or error.
* Reference checks.
  * After the writer, and after each fix round, the host rebuilds them and grades them three times on the reference and
    once on the development no-op.
  * The review loop runs as in D33: a review, then, while its verdict is needs_fix and fewer than 2 fix rounds have
    run, a fix round and a new review. After the loop the checks are frozen, whatever the last verdict.
  * They are usable when, in the last validation, the reference passes in all three repeats and the no-op's outcome is
    a task failure. Otherwise they are unusable: D19 then has no first source for the family, so each of its D19
    proposals is ambiguous (a missing decision, D19).
  * The host writes `verifiers/reference_check/status.json`: status (usable or unusable), fix rounds and reasons.
    `scripts/propose_labels.py` and the pre-flight are to read it before any natural label is proposed; neither does
    yet. The family stays in `natural-pr-v1`: its source-evidence estimand and its second labeling do not depend on
    the reference checks.
* Labeler. The host builds it and grades it three times on the reference and three times on the development no-op.
  * A check misses the change when CHECK_REQUIREMENTS maps it to a change requirement of the reference contract and it
    passes on the no-op in some repeat. A change requirement is detected when a check mapped to it fails on the no-op
    in all three repeats.
  * The labeler is usable when the reference passes in all three repeats and every change requirement is detected:
    §15.5 says it "must pass on the reference and fail on the no-op for every requirement the task changes". This is
    stricter than D55's coordinator, which marked unusable only a labeler that failed on the reference; D55's four
    labelers met both conditions.
  * A labeler that is not usable as written gets its one revision if at least one check can be named. FAILING then
    holds the checks that failed on the reference in some repeat and the checks that miss the change. A change
    requirement with no check mapped to it cannot be named (§19.8), so when it is the only problem, no revision runs.
  * After a revision the host grades the labeler again in the same way. `status.json` records the status, the round (1
    as written, 2 after the revision) and the reasons, and the labeler is frozen. An unusable labeler is left out of the
    second labeling and reported (§15.5).

**Agents.**
* Configuration A (the session's default model) for every role except the labeler writer and its revision, which are
  configuration B (the smallest tier the agent tool offers). Model identifiers stay in the private run records.
* Tools: Read, Write, Edit, Glob, Grep and Bash. No WebFetch, WebSearch, task tools or agent spawning, where the agent
  tool allows the restriction; where it does not, the run's tool set is disclosed.
* Harness context: no task list of the build session in an agent's context, where the agent tool allows it (§18.3);
  otherwise it is disclosed as in §18.2.
* Absolute paths only, and one new workspace per run.
* Budgets as the templates set them: 6 to 14 tests per generator, 6 to 16 per reviser, 8 to 20 reference checks, 4
  attacks per variant, up to 4 runs of `check-proposals` per proposer (a first run and at most 3 more), 3 revisions
  per audited verifier, 2 fix rounds of the reference checks and 1 labeler revision. There is no wall-time limit;
  turns, tool calls and wall time are recorded for every run.
* Re-run rule: a generator run that registers nothing (no proposals, no test file, an unchanged state) is re-run once,
  in a new workspace, with the same template and the same values except WS (so its prompt has another sha256), and the
  re-run is recorded. Nothing is regenerated because of a check or grade outcome.
* A contract whose explicit requirement still quotes a non-user event after its proposer's runs is recorded as it is.
  The acceptance gate's reason (`non_user_evidence`) is reported for the family, and the run, an automated pilot,
  grades the family as it is.

**Generation records.** Every contract, verifier and constructed candidate carries one, made by
`scripts/agent_run_record.py` from the run's transcript: the configuration label, the prompt sha256, start and end,
turns, tool calls, wall time and a session-relative pointer to the private run record. No model identifier. An
audited verifier's record combines its generator and its revisers (`--combine`). A pool candidate's `started_at` is
the evidence of the freeze order.

**Audits.** Every natural agent's transcript gets the natural-agent:v1 profile: the fresh-attempt profile over tool
inputs and tool outputs, with the CLI allowlist (`<repo>/.venv/bin/tracecontract lint-tests|check-proposals` on the
agent's own files), the network rule and the tool set. The labeler writers and their revisions also get the D58
labeler profile, parametrised by task directory and snapshot root. Every flag is read in the transcript and assessed
in writing, with the categories of §18.1 applied by analogy. The records go to
`data/natural/tasks/<id>/labels/generator_audit.json`, one entry per workspace of the table above; only counts and
verdicts go into the index. A near-miss generator whose transcript shows a run of the repository's tests on its state
(through `run_python.sh -m pytest` or otherwise) is not excluded, since it read nothing outside its workspace. The run
is assessed in writing in its entry and disclosed with the family's B1 results, since the near miss could then have
been fitted to B1's tests.

**Retention.** Private run records go to `/home/user/nat_runrec/<task>/`. A byte copy of the labeler workflow script,
the source of the two labeler templates (sha256 `68599d2f...`), was kept under `/home/user/nat_runrec/` before the
first natural agent. Its only other copy lies in the build session's directory, and an export of it would be redacted
(it names a session-local path and the agents' model option), so the export would not hash to the templates'
`source-sha256`. `check_natural_prompts.py summary --source-dir` with that directory compares the two templates with
it. `/home/user/nat_ws` and `/home/user/nat_runrec` are archived into the sealed directory after the run, as in D50,
and before any later fresh-agent round.

**Decisions.** These are builder defaults. The owner may change any of them before the first natural agent; a change
after that is a deviation, logged before its use (D33, D41).
1. Construct. A PR reviewer's comment is treated as the correction, and the reviewer is usually not the requester.
   The paper reports this as a construct difference from in-session user corrections.
2. Publication. Thread-derived material (contracts, generated tests, candidates, rendered sessions, raw results,
   reports) stays under `data/natural/`. Only ids, outcomes, counts and hashes are committed.
3. B1. §17.2 is kept as hashed, with no amendment. Disclosed: B1 equals the D19 regression norm in NP-03, NP-05 and
   NP-20, and in part in NP-19. The held-out alternatives run the base-test subset (TESTS) with `run_tests.sh`; in
   NP-03, NP-05 and NP-20 its files are B1's own, so these alternatives are developed against B1's tests, as the
   controlled alternatives ran the repository's tests. TESTS can name the repository's package (NP-03). The prompts
   stay in the private run records, and the natural export of prompts withholds one that names a natural repository
   (`export_prompts.py --natural`).
4. Second labeling. A labeler pass on a `natural_pre_review` state counts as ambiguous, which mirrors D19's natural
   rule.
5. Freezing. §15.5's rule for natural tasks reads "before any generated held-out candidate exists". The pre-review
   state has existed since S10, and no labeler writer can access it.
6. B3. Per-test selection: a kept test passes on the reference in three single grades and fails (failed or error) on
   the development no-op (`scripts/select_b3_tests.py`). §19.7 lists what is graded before building stops: the audit
   loops (development candidates), and the reference checks and the labeler (reference and no-op). This entry reads it
   as allowing B3's selection grades too: they grade only the reference and the development no-op, and §15.6 needs
   them (B3's tests must fail on the base and pass on the reference). A family left with no test has B3 unavailable.
7. D19 for natural families uses 3 repeats. Repeats that disagree are a missing decision, so the label is ambiguous.
8. There are no human labels, and no review packet is prepared now.
9. Provenance eligibility stays `pending_review`, so every natural evaluation is an automated pilot (`--pilot`).
10. No sensitivity view clustered by repository while the arm is in case-study mode (below 10 tasks). With 10 or more
    tasks, one exploratory view clustered by repository is reported.
11. Network. It is enforced by the tool set where the agent tool allows it, and by the natural-agent audit's network
    rule with a written reading of every flag.
12. Harness. The image smoke test passed in all six images (2026-11-21T15:21:27-15:24:25Z, `tc-harness/0.3.5`; record
    sha256 `333c2671...`, kept with the private run records): FX-01's reference passed and FX-01-wrong was a task
    failure, three repeats each, under the FX-01 verifier and a probe verifier. So the harness is not changed.
13. Retention: as above.
14. Near-miss targets, fixed by the host from the frozen reference contract before P6. A correction requirement is a
    scored, active requirement introduced at the review comment or a reply (as `contract.correction_event_ids` and the
    pre-flight read them); under (k), none rests on the diffs alone. Requirements are taken in the contract's order,
    change requirements first.
    * nm-1 and nm-2 take the first two correction requirements; if there is only one, both take it.
    * nm-3 takes the first other scored active requirement (each is introduced at the issue). If there is none, it
      takes the next correction requirement not yet taken, and failing that nm-1's.
    * A near miss whose target an earlier near miss already has is the variant shared-target (deviation h).
    * If the reference contract has no correction requirement (the drafter says why), §15.6's "at least two of which
      target the correction" cannot hold. nm-1 to nm-3 then take the scored active requirements by the same order and
      reuse rule. The family still enters `natural-pr-v1` (§19.7): the first estimand of §15.6, the pre-review
      acceptance under the source-evidence label, rests on the reviewer's request, the addressing commit and the S9
      agreement, not on the reference contract. Its tables say that the reference contract does not observe the
      correction and that no near miss targets it; its pre-review state is ambiguous for D19 if the reference checks
      pass it (§15.6). The pre-flight fails such a family as it stands (fewer than 2 near misses on a correction
      requirement); before the run it is to report the case as a note citing this entry.
    * A reference contract with no scored active requirement stops the family at P4, and the owner decides.
15. Advisory construction checks are not run for natural families; §15.6 does not require them.
16. Owner masking through the GitHub account type is deferred, since nothing thread-derived is published.
17. Deviation (i). The owner-context line is left out of the six templates that carry it. It asserts the owner's
    standing instruction and approval, which a template fixed now cannot vouch for when its agents run. Leaving it out
    changes no task instruction, input or output. If the owner restores it, the six templates are new versions,
    hashed in a new entry before their next use.

**Differences from the controlled recipe, disclosed.**
* The natural labeler reads the workspace's rendering of the reference contract (`contract.json`, with the active
  scored requirements: id, kind, statement, observable and the user turn that introduced each; and `instruction.md`).
  The controlled labelers read the stored contract file. The natural labeler sees no evidence quotes and no unscored
  requirement.
* The natural labeler reads excerpts of the harness module and of the verifier module (their docstrings, the harness's
  public API and the lint code, copied verbatim), where the controlled labelers read the whole files.
* The labeler revision is told check ids only, without the kinds and the uncovered requirements that D55's coordinator
  gave (§19.8, D58); a labeler that does not detect every change requirement on the no-op is unusable.
* The reference checks are validated by the host and reviewed for every family (D33 did so for CS-02 only), and get a
  status record.
* The two mappers' prompts differ only in the workspace and the mapper label. Both carry D41's sentence on
  contradiction claims, which the frozen held-out template already holds.
* Near misses: one agent each, with targets given by the host, and one fixed sentence for a near miss that shares its
  target (deviation h).
* The owner-context line is left out (deviation i).

**References to this entry.** The recipe was planned as D61, and these files cite it so:
* `src/tracecontract/analysis.py`: `NATURAL_DECISION`, which the natural analysis writes into its rule texts;
* `scripts/propose_labels.py`: its docstring, its refusals and the rule it writes into `labels/proposed_labels.json`
  ("repeats: D61");
* the docstrings of `scripts/select_b3_tests.py` and `scripts/agent_run_record.py`;
* `tests/test_natural_labels.py`, which expects "(D61)" in a refusal.

`tests/test_preflight_natural.py` expects the pre-flight to cite no entry after D60 until this one is numbered. D61 is
the fresh-v1 run. These citations are to name D64 before any natural label is proposed or any natural analysis is run;
none exists yet.

### D65. F2 for the six accepted families: rendered inputs and proposer prompts, logged before the first proposer; host coordinators, agent options and the order record
This entry is F2 of D64 for NP-03, NP-04, NP-05, NP-18, NP-19 and NP-20, the six accepted families of the first sample.
It is committed before any of their contract proposers starts. At this commit no natural agent has started: the build
session's workflows have run host steps only (workspaces and rendering), and no natural contract, generated verifier,
held-out candidate or label exists.

**Rendered inputs.** The sha256 of the bytes of each family's `session.txt` (as the contract-full workspace holds it),
`session_first_prompt.txt` (the contract-initial workspace's) and `reference.diff`. No workspace that holds
`reference.diff` can be built before the contracts exist, since the testgen roles read one, so it was computed with
`scripts/make_agent_workspace.py`'s own functions: the reference candidate's patch through `filter_patch` with the
default protected set, written as UTF-8 text, as the tool writes it. Before the P2 prompts are rendered, the host checks
every P2 workspace that holds a `reference.diff` against this table; a mismatch stops the family.

| Family | `session.txt` | `session_first_prompt.txt` | `reference.diff` |
| --- | --- | --- | --- |
| NP-03 | `8d351bd47f121050ced92499d5247093ade676e11074c52c21851475c51b4f12` | `17f6fdd9dbfabaa032d436bac995b7767718631abd7acc50b3fb4a00ee180465` | `6e6ee6cf5f141c89700bcfac56f3149c08bbab353c2028ba58a93e14b1f8cba7` |
| NP-04 | `a67d895cd9cbbf27e90b817f2e8242d006ce2c4f9b9f1d8c861dca0a4bc82c30` | `be0dcd5c618d1f28d3cd04c60eb834ccb9fc6f6335b5425df8662659c51fd752` | `f724cba41a738440c28cff5ee28fd235416013f1a6d4bf4677b4187d2aaee2e1` |
| NP-05 | `1b09f4beea4c9bab2fa768040acdd9bd0c86b508270be477af5720792bea3f04` | `7680f5b2543972126f736cb3f302917cc5695888e82bdda25ae1c5b9908549e9` | `8941435653380e403f2833faffb8671dcbf2a8c9da3e213086760c4e6b6ff679` |
| NP-18 | `735dc4d0de95b3445697055b55cddcbd00e27746021628edc4a6032b3f0e5ca8` | `50e6f80ca39e0ba12b1c8dfbf3bad13bf4aa44394623a377a13561c883ac8ddc` | `c31d5050f77af7a4d9cb60b894a0817a77b7d2ad589e05930d5fa74143441b0b` |
| NP-19 | `052057237e7f6040614bbfd3182297e7b5bda1ff3245bc2e4932b06c6599a07a` | `1347bf4c406011e49ae9d8d2029e8444ef3182a3639e57e7f0a6f97693357911` | `ce8b36eaad377a444b09ffd50dcab5f9922803829ac3a1dac8818865e9b82316` |
| NP-20 | `2a4cf8d2f695f08362ff9096114780a41481d361db5dc8b8a99c1edb37817e59` | `ebc1e861614074409c4a84752e3883fa7c97763bff66ba571e6ca5965561ba53` | `9f52df4a830579dae1171a9d6390980fbfeef6fbc398f0e8b3b4b1433eaea4a4` |

Sizes in bytes, in the same order: NP-03 4,066, 645 and 14,826; NP-04 1,365, 434 and 1,471; NP-05 6,758, 1,800 and
6,547; NP-18 3,170, 2,146 and 1,765; NP-19 3,166, 2,149 and 44,300; NP-20 1,920, 1,045 and 7,500. The hashes are of the
bytes. NP-18's `session.txt` holds 3 CRLF line ends, all in the review comment, and NP-19's session texts hold 54
(`session.txt`) and 52 (`session_first_prompt.txt`), so a read that normalises line ends does not reproduce them. A
quote copied across such a line end is an exact substring only with its carriage return; check-proposals reports one
that is not, and the proposer's fix loop covers it.

**Proposer prompts.** contract:v1-natural (sha256 `7fae39f9...`, D64), rendered with its only host values: TASK, WS
(the proposer's workspace) and SESSION_ID (the session id of `session.json`). The sha256 of each prompt as it will be
sent:

| Family | contract-initial (initial_only) | contract-full (full_session) |
| --- | --- | --- |
| NP-03 | `8e9d5ca09c4e797d5c4af5b1e7d01e3630c08ae47ed66827c013af13cfb34d17` | `3870fb21307daf7ac991a2f13ae8ec6b8ff3371d5a25e90668fa98ec8257b5bb` |
| NP-04 | `3eecae0149b32a535e7d335e50297ec04135492fe0ddbcfef0d5158deebfdcb0` | `723226b015e0830bdc5da32a8cabe1d6c855227b30108a3761acefa38d7273d4` |
| NP-05 | `5069a7c14c530d00a404fac53b5d89cd04dd8f7edd0c2913519006811de814dc` | `7e8f53fbe341bba5f131ded0975362b1dc9848879b0f655c2948a777ebc9ae7b` |
| NP-18 | `d216e3b8ef6f817e560e3a3c129d91db80c12ec2c7be3e8593a54f9686196b5e` | `7fc926971932aa8aad41c66d0e677f8421991968226442925ae0323d98f85809` |
| NP-19 | `f7a4a050e313a46de4bc2f355b50c325e2284b70f3f12320274d5bc82421b936` | `c2e8816b9d32d21b1b784c067adfd89c6a8af799c8fe8aceb2a4b67e1bd7dc1a` |
| NP-20 | `fcde7b380645a1fe968e3d70f7f9f2fe16a59e93cd8d47373f3f177a26b9d916` | `6935adcfa5a71beecf4f8101af179342bee794b84554c52d6b10b31bc3e546c3` |

The prompts are kept with the private run records.

**Checked by the build session.** The coordinators' reports were not taken on trust. The build session recomputed the
18 input hashes from the workspace files and the task data, with the tool's functions; ran `render --verify` on the 12
saved prompts (all equal); and checked that the 12 workspaces hold only `manifest.json`, an empty `scratch/`, the
session file and `session_events.json`.

**P1 preparation.** One host coordinator per family (next paragraph; two for NP-19, below) built the two proposer
workspaces, computed the inputs above and rendered the two prompts, finishing at 18:41Z.
* Each host log has back-filled entries, marked as such: read-only inspection run before the log existed, and shell
  pieces run outside the logging wrapper.
* NP-19's first preparation was stopped by an interrupt of the build session's workflows. Its partial records were set
  aside in the private run records and the step was redone from the start. NP-20's coordinator read the tail of that
  set-aside host log to follow the same procedure, and says so in its own log.
* One directory listing in NP-19's log caught a held-out candidate's file name (another family's pre-review state),
  written by the S10 step of the S9 extension, which was running at the same time. The coordinator replaced the name
  with a placeholder and logged the redaction.
* None of this reaches a generator: the prompts and workspaces are as checked above.

**Host coordinators.** D64 gives every host step to the build session (D24). They are run by host coordinators:
subagents of the build session, in configuration A, one per step, inside one workflow per family and phase.
* A coordinator runs only the repository's CLI and scripts, and shell commands on files. It writes no generated content
  (requirement, test, contract, state or candidate), never repairs a generator's output, writes nothing under
  `data/manifests/`, and never commits or pushes.
* It logs each command as it runs to the family's host log in the private run records (time, command, exit code, short
  output). An entry added afterwards is marked as such. It keeps its helper scripts with the family's run records, and
  reads only its own family's task directory, workspaces and run records, besides the repository's code and documents.
* Values taken from an agent's run, such as a review's issues, a near miss's description or a mapping file, are read
  from the run's transcript or workspace by a script, never retyped.
* The generators are separate agents, started by the workflow, not by a coordinator. A coordinator returns each prompt
  as the renderer printed it, with its sha256. The workflow computes the sha256 of the text it is about to send (UTF-8
  bytes; a plain implementation in the script, tested against a standard one) and sends it only if the two agree. On a
  mismatch it asks the coordinator once more, then stops the step. The coordinator of the next step checks the first
  message of the generator's transcript with `render --verify` before making its generation record. So no
  coordinator's context reaches a generator, and every prompt is checked twice.
* Coordinators can read the study repository and the private run records. Generators cannot (deviation c), and their
  audits check it.

**Agent options, as the source workflows set them.** D64 fixes the templates, not the agent options, which follow each
template's source workflow.
* Roles from the generate workflow run as the default workflow agent, with no output schema, as `wf_b796bb4f-1dd` ran
  them: the contract proposers, the C1, C3, B2 and B3 generators, the attacks, the development alternatives, the
  revisers and the reference-contract drafter (refcontract:v1 and b3:v1 are new templates from that workflow's
  CONTRACT_PROMPT and TESTGEN).
* Roles from the held-out workflow run with agent type general-purpose, as `wf_b428f318-391` ran them: the
  reference-check writer, reviewers and fixers, the pool's alternatives and near misses, and the mappers.
  * The reviewers have the source's review schema (verdict, issues, coverage, validation), which the review template's
    header names. The workflow reads the verdict from it, and the coordinator takes ISSUES from the review's structured
    output in the transcript.
  * The source's generation schema asks for the candidates an agent registered. Under deviation (b) the host registers
    them and the templates ask for a text answer, so those roles have no schema.
* The labeler writer and its revision run as the default workflow agent in configuration B, as the labeler workflow
  `wf_5db2f657-fdf` ran them.
* Configuration B is the smallest model tier the workflow agent tool offers; configuration A is the session's default
  model.
* A workflow runs at most two agents at a time on this machine. The five pool agents of P6 are started together and run
  at most two at once. None is given another's output, which is what D64's "in parallel" requires.

**Harness context and tools (§18.3, D64).** The build session's task list was emptied before this commit, so no task
title reaches a natural agent's context. The workflow agent tool offers no per-call tool restriction. A custom agent type
would give the generators a system prompt the controlled generators did not have, so none is used. Each natural agent
therefore has its agent type's tools, as the controlled agents of the same source had, and the natural-agent audit reads
every network use and tool call (decision 11). An environment block naming the study repository as the working
directory stays in every agent's context, as §18.2 discloses for fresh-v1.

**Deviation (i) and the owner's review.** Three records disagreed on deviation (i):
* D64 takes it as a builder decision, pending the owner's review (decision 17).
* The templates' README, as committed in `a86c2a0`, said it holds only once the owner has accepted it, before the first
  natural agent starts. `79a2335` brought the README in line with D64.
* The headers of the six templates that carry (i) say it holds only once the owner has accepted it. The headers are
  comments: they are hashed with the template, but no rendered prompt contains them.

NP-04's coordinator read the README before `79a2335` and asked that the owner's acceptance be confirmed before the first
proposer. It is not on record: the owner has not reviewed (i), or the other builder decisions of D64. D64 is the record,
so its decision 17 holds, and this entry supersedes the six headers' sentence; the templates are not changed, so their
D64 hashes stand. The proposers are not affected either way, since contract:v1-natural carries no deviation (i). The six
templates that do carry it are first used at P5. If the owner restores the line before then, they become new versions,
hashed in a new entry before their first use. After that, a change is a deviation logged before its use (D64,
Decisions).

**The order record.** D64 ends each phase with an index commit, and the commit times are the order record. The committed
index (`data/manifests/natural_tasks_index.json`) is being rewritten, uncommitted, by the S10 step of the S9 extension,
with code not yet committed either, so an index commit at a phase end would carry that work half done. Until that work
is committed, the commit at a phase end is of a log instead.
* `scripts/record_phase_end.py` appends one line per family and phase to `data/manifests/natural_phase_ends.jsonl`. The
  line holds the family's task directory in the index's own form (`natural_pr.file_hashes`, which the S10 work does not
  change), its verifiers with frozen and frozen_at, its contracts and its candidates: ids, hashes, counts and times only.
* The builder commits that file alone after each phase of each family. The family's next phase starts only after that
  commit.
* Before P6 (F7), the commit recording P5's end is also pushed. So each family's frozen reference checks and labeler are
  published before any held-out candidate of it exists.
* The index itself is committed with the S10 work, and again after P7. Within a phase, the generation records
  (started_at, ended_at), the verifiers' frozen_at and the host logs give the order.
* Each phase is one workflow: preparation (the workspaces and prompts of the phase), the generators, then registration,
  with the loops of P3 and P5 inside their phase. A re-run's workspace and label carry the suffix `-r2`, so that its run
  id is unique.

### D66. S9 extension corrected without a fetch; the build stops at a usage limit; unfinished packages kept as patches; the manuscript rebuilt around fresh-v1
**S9 correction (protocol §19.2; corrects D63).** Of the comments that D63 left unjudged as over the caps, 5 had every
object their diff needs already in the bare clones.
* A step checked this without any fetch: a temporary view of each clone with no promisor remote and no remote, its
  objects reached through alternates, transports disabled and lazy fetching off. Git's trace shows no child process, and
  the clones are unchanged (paths, sizes, modification times and modes equal a baseline taken first).
* The 5 were batched (batch 17) with the extension's own diff code. Two new configuration-A judges, with the extension's
  templates, fail all 5 as asking for no behaviour change or defect fix, and agree on each. So the correction adds no
  qualifying comment and no PR: the families NP-26 to NP-44 and the reserves NP-45 to NP-48 keep their ids, PRs and
  corrections.
* Corrected extension counts: 405 judged (D63: 400), 10 disagreements, 433 failed. Before judging, 129 fail (D63: 134):
  59 over the caps (65), 56 not fetchable and 14 with no later commit (13). D63's "44 lack a commit or the PR head" reads:
  43 lack both the reviewed commit and the PR head ref, and 1 fails criterion 2 (no later commit changes the commented
  file). 91 of 534 comments qualify (17.0%), 91 of the 405 judged (22.5%, Wilson 18.7% to 26.8%; D63 gave 22.8%). κ is
  0.9535, 0.893 and 0.9371. Both samples together hold 122 qualifying comments on 55 PRs.
* D63 also says that only NP-05 is affected among the built families. The first-sample PRs with a qualifying extension
  comment made before their correction are NP-05, NP-09, NP-10, NP-11, NP-24 and NP-25; NP-09 to NP-11 were built at S10
  and rejected. NP-05 is the only accepted one, and the plan is unaffected, since first-sample families keep their
  corrections.
* Records: `screening_natural_aidev_s9x.json` (aggregated again); `rejection_ledger.json` (6 rows change their reasons;
  550 S9 rows and 16 S10 rows); `natural_tasks_index.json` (48 rows: 6 passed, 16 rejected, 26 not built; 6 at S11). The
  index writer (`natural_pr.write_natural_index`) now records both samples' S9 outcome in the index's header
  (`s9_complete`, which the pre-flight's stop rule reads, §19.5), and gives a rejected family's place only to a reserve of
  its own repository and its own sample (§17.3, §19.3 as D63 reads it). No row has `replaced_by`.
* An independent read-only check confirmed the plan and the privacy of the five changed files.

**The build stops at a usage limit.** At about 18:50Z on 2026-11-21 the build session's agents reached the account's
weekly usage limit, which resets on 2026-11-25 at 07:00Z.
* The S10 step of the extension had started and was stopped. It left 10 compiled task directories (NP-26 to NP-35)
  under the git-ignored `data/natural/tasks/`, without their S10 outcome. The index does not record them, and they are to
  be built again from the start.
* The natural recipe (D64) has not started: no natural agent has run. F2 (D65) stands, and the six families' workspaces
  and proposer prompts are ready.
* The owner then asked the build session to wrap up. The natural arm is left at F2, with its results pending.

**Unfinished packages kept as patches.** Two code packages for the natural arm were written and reviewed, but their fix
rounds did not run: the analysis of natural runs (WP-G) and the privacy and publication tools (WP-H1).
* WP-G's review found no high-severity defect and two medium ones, and 5 of its tests fail.
* WP-H1's review judged it not ready as a privacy gate (one high-severity defect: a short thread text is never matched).
* Neither is needed by a reported result. Both are kept as patches against `11d7996`, with their status and the open
  findings, in `docs/wip/`, outside the code tree. WP-H1's three protective `.gitignore` rules are committed.
* Both are to be finished before `natural-pr-v1` is analysed or published.

**The scan's sample coverage.** The committed scan (`scripts/scan_tracked_files.py --aidev-logins`) loads the logins
connected to the first S9 sample's 150 comments (119), not to the extension's 534. The independent check above found this.
* A one-off scan that loaded both samples (219 logins and names) read the working tree and the commits a push would send.
  It found no person's login. Its only findings, 195 lines, are one organisation account that the study names
  independently of the natural sample, mostly inside URLs and citations.
* A suppression option for such accounts was drafted and withdrawn: a scan that drops findings by a private list would
  weaken the gate.
* The committed scan is unchanged. Extending it to both samples needs a decision on organisation accounts, which is the
  owner's. Every push so far was gated by the first-sample scan.

**Manuscript.** The paper is rebuilt findings-first around fresh-v1, from a written plan.
* Agents rewrote the abstract, introduction, related work, data, method and protocol sections before the limit, and
  added table modes to `paper/make_tables.py` (`--fresh`, `--regrade`, `--natural`), `paper/make_figures.py` and an
  evidence ledger for each.
* The build session wrote the results sections (fresh-v1 first; the natural funnel, with every natural result marked
  pending; the construction pilot as a development study, with the 0.3.5 re-grade), the fresh-v1 part of the qualitative
  analysis (from D62), the stale statements of the limitations, ethics and reproducibility sections, and the appendix
  tables.
* Every number in the new text is a macro of the generated number files or a count recorded in the decision log.
* Not done from the plan: a number checker for the text (`check_numbers.py`), the split of the appendix and the planned
  length.

**Still open.** The D64 citations in code (`NATURAL_DECISION` and the other places D64 lists) are to name D64 before any
natural label is proposed. The natural recipe P1 to P7 for the six families, labels, the pre-flight, the run
`natural-pr-v1` and its analysis follow D64 and D65 once agents can run again.

### D67. Harness context of the natural agents: the owner's latest message is relayed before the computed task
The natural arm's generation started on 2026-11-22 at about 01:55Z, after the usage limit reset (D66). The owner asked
the build session to keep going while using at most half of the plan's total usage. The P1 coordinators of NP-04 and
NP-19 found that each workflow agent's context begins with a harness entry, `[Workflow harness — user request]`. The
entry relays the owner's latest message, here in two lines (487 characters), before the computed task.
* The entry lies outside the template and outside the prompt hash. `render --verify` and `scripts/agent_run_record.py`
  read the computed task, so every prompt check of D65 holds.
* The entry is not new. Every agent of the controlled generate workflow (`wf_b796bb4f-1dd`, 20 of 20) and of the
  held-out workflow (`wf_b428f318-391`, 11 of 11) carried one, relaying the owner's message of that day. The labeler
  workflow (`wf_5db2f657-fdf`) and the fresh-v1 attempts carried none.
* The natural agents of this round therefore see the owner's message about the usage budget. It names no task, input
  or output. It could still nudge an agent toward less work, so the natural-agent audit of P7 assesses each transcript
  for that, and the analysis reports the turns, tool calls and wall time of every natural run (D64, "Agents").
* The entry belongs with the harness context that D65 discloses (the environment block). Like the environment block,
  it cannot be removed where the agent tool gives no option to remove it.

### D68. Round 5 under a usage cap: leaner host coordinators, a correction to D67, Docker restarted, and how far the round goes
**The cap.** The owner asked the build session to use at most half of the plan's total usage in this round. The
workflows' reported agent tokens give the measure. Last week's limit was reached at about 82M (2026-11-18T07:00Z to
2026-11-21T18:55Z), so the round's natural work is planned at about 40M.
* Measured per family: P1 about 0.6M and P2 about 2.4M (NP-04).
* Most of P2's cost is cache reads of long contexts, and about half of it comes from the two host coordinators: some 85
  turns each, on a context of about 250k tokens.

**Leaner host coordinators.** From the phases launched after this entry, the coordinators run at a lower reasoning effort
than the session's default. They also get one more rule: send long command output to files, print short summaries, do
not re-read files, and combine a sub-step's commands in one logged helper script
(`experiments/natural_workflow/natural_phase.js`). Coordinators are not generators: no template, prompt, agent option of
a generator or step of the recipe changes. NP-04's P3 was launched before this change.

**Correction to D67.** The relay of the owner's latest message is present only in workflows launched in a turn that
answers an owner message. These are the P1 runs of the six families (their proposers and coordinators). The P2
generators, launched in turns that answer task notifications, carry none (NP-04's P2 coordinator checked all eight).
The natural-agent audit of P7 records it per transcript.

**Docker.** The machine restarted at about 01:49Z, and the Docker daemon did not come back: the service script fails at
a `ulimit` call in this container. NP-18's first P2 preparation found the daemon down and stopped at its first
workspace, before building or rendering anything. The build session started the daemon at 02:21Z, its images
unchanged, and the step ran again in a new workflow (`wf_e11328a2-e72`). The other families' preparations reached
Docker after it was up.

**How far the round goes.** Within the cap, the round runs P2 to P4 for the six families: every natural verifier and
reference contract is frozen. P5 to P7, the extension's S10 and the run follow in a later window.
* §19 bars grading a natural verifier on held-out candidates before building stops (30 accepted, or all families
  processed). The extension's S10 is part of building, so `natural-pr-v1` waits for it in any case.
* If the measured cost runs ahead of the plan, the round stops at the last completed phase boundary, with its phase-end
  record committed.

### D69. The natural analysis (WP-G) and the privacy and publication tools (WP-H1) finished and merged
Both packages kept as patches in D66 were finished in isolated worktrees, each with one review and, for WP-H1, one more
fix round. They are merged as finished, and `docs/wip/` is removed.

**WP-G (analysis of natural runs).**
* The two medium findings are fixed.
  * The cost per accepted task counts S10's build time, fetch seconds and fetch bytes on one basis: every family S10
    processed, rejected ones included, per accepted task. The accepted families' own S10 time is reported beside it.
  * `report.py` builds a case-study report (fewer than 10 S11 tasks): per-family tables, no pooled rate, interval or p.
* The low findings are fixed. Five tests the patch had left stale are reconciled: in each, the implementation was right.
* The recipe's citations name D64, as D64's "References to this entry" asks: `NATURAL_DECISION`, `propose_labels.py`
  (whose rule text now reads "repeats: D64"), the docstrings of `select_b3_tests.py` and `agent_run_record.py`, and
  the pre-flight's natural rules with their tests.
* The recorded runs regenerate as before. `analysis.md` and `report.html` of all seven runs are byte-identical under the
  old and new code, and `analysis.json` differs only in code hashes and the revision. `verify_frozen_inputs.py` passes.
* The second review found no high or medium defect. Its low findings stay open:
  * the HTML report leaves out two natural caveats that `analysis.md` gives;
  * some HTML cells do not mark B3 as secondary;
  * the not-recorded note on costs does not yet cover the extension families to be rebuilt (D66).

**WP-H1 (privacy and publication tools).**
* Both reviews' high and medium findings are fixed, each with a test:
  * a short thread text is matched whole;
  * the export guard no longer aborts on its own words;
  * traceback frames of a task's own package are kept;
  * check ids and the code of patches, verifiers and base snapshots are checked outside the publisher too;
  * every task directory is read, and an unreadable file fails closed;
  * the publisher fails closed when its code check cannot run.
* `--aidev-logins` is unchanged (the first S9 sample, D66). Without the new flags the scan's output is byte-identical to
  before.
* **Builder defaults, pending the owner's review:**
  * the minimum for a whole-text match: 3 words, with a letter in at least two tokens, and 12 characters; or 8
    characters of a script without spaces;
  * whole matching of every author's texts and of contract quotes;
  * traceback header lines cut as tool output;
  * the own-package rule for traceback frames;
  * the bare-name scope: the natural arm's own files within `tasks/`, `data/`, `results/` and `experiments/`;
  * the code-line exemptions: `src/`, `scripts/`, `tests/`, `tasks/CS-*`, `data/controlled/` and `paper/*.py`, plus
    `docs/wip/*.patch`, which holds nothing now. A code line also needs a word of 4 or more characters;
  * a base-snapshot line counts if one of its words occurs in at most one line of the corpus from before the natural
    arm. It is not reported in the study's code or the controlled arm's outputs, and the publisher checks every line;
  * the screening texts are optional in the scan and required by the export guard and the publisher. Requiring them
    in the scan reports texts that the controlled arm's own records already held.
* **Known gaps.**
  * A repository name that is also an ordinary word is not reported in `docs/`, `paper/`, `src/` or commit messages.
  * The repositories of NP-07, NP-08 and NP-12, and of the screened comments never built, are unknown to the scan.
* From this entry, the pre-push scan also runs with `--natural-texts data/natural/tasks`. At this commit it finds
  nothing over 32 tasks, in 95 s.

**Two tests that assumed no natural record existed are narrowed.** Each check stays as strong for the controlled
records and becomes stronger for the natural ones.
* `tests/test_schema_identifiers.py`: a natural contract or constructed natural candidate must carry a complete
  generation record (D64). S10's candidates and the controlled records carry none.
* `tests/test_audit_record.py`: a natural audit record holds every iteration from 0, with one revision between
  consecutive ones. The controlled audit records hold none.

The full offline suite passes: 1090 tests, with the real natural data present.

### D70. Round 5 closes at P4: what was built for the six families, and what the construction shows
All six accepted families went through P1 to P4 of D64's recipe (2026-11-22, 01:55Z to 08:46Z). Each phase end is a line
of `data/manifests/natural_phase_ends.jsonl`, committed and pushed before the family's next phase (D65).
* For every family: the initial-only, full-session and reference contracts (F3, F5), and the seven verifiers.
  * C1, C3 and B2 were frozen together (F4).
  * C2 and C4 were audited and frozen.
  * B3 was selected and frozen.
  * B1 has been frozen since P0.
* As D68 planned, P5 to P7, the extension's S10 and the run `natural-pr-v1` follow in a later window.
* The round used about 37.2M reported agent tokens since the reset, within the plan of about 40M. Per family: P1 about
  0.6M, P2 2.3M to 3.3M, P3 0.7M to 2.8M and P4 about 0.4M to 0.5M.

**Counts** (no text; from the task directories):

| Family | Reference contract: requirements / scored active / at the correction | Scored active, initial-only / full-session | Checks: C1, C3, C2, C4, B2, B3, B1 |
| --- | --- | --- | --- |
| NP-03 | 9 / 7 / 2 | 4 / 6 | 11, 14, 14, 15, 14, 11, 954 |
| NP-04 | 5 / 4 / 2 | 3 / 3 | 11, 14, 12, 14, 11, 14, 34 |
| NP-05 | 13 / 10 / 2 | 10 / 11 | 14, 14, 14, 15, 12, 14, 354 |
| NP-18 | 5 / 4 / 2 | 5 / 3 | 12, 11, 12, 12, 12, 13, 26 |
| NP-19 | 5 / 4 / 2 | 4 / 3 | 10, 11, 13, 15, 13, 8, 1 |
| NP-20 | 16 / 12 / 5 | 3 / 5 | 12, 13, 13, 13, 12, 11, 48 |

"At the correction" counts the scored active requirements introduced at the review comment or a reply. B3's per-test
selection kept every test in all six families.

**Audits (audit:v1) of the 12 audited verifiers.**

| Family | C2: revisions, final result | C4: revisions, final result |
| --- | --- | --- |
| NP-03 | 2, passed | 3, failed (reference not passing) |
| NP-04 | 3, failed (false rejection of the development alternative) | 0, passed |
| NP-05 | 3, failed (false acceptance of a development attack) | 3, failed (false acceptance of a development attack) |
| NP-18 | 1, passed | 1, passed |
| NP-19 | 2, passed | 3, failed (reference not passing; the last revision changed nothing) |
| NP-20 | 1, passed | 0, passed |

* 22 revisions ran in all. Seven verifiers pass, and five are frozen with a failing audit after their third revision,
  as D27 requires.
* A revision that changed nothing was re-run once under D64's re-run rule, in NP-03, NP-05 and NP-19.

**What the construction shows.** These are observations of the build, made by model agents and not reviewed by a person.
They are not results of the natural arm, whose run has not been made.
* The natural reference often fails the contracts recovered from its own thread.
  * At iteration 0 the reference fails 9 of the 12 audited verifiers (`reference_not_passing`), in five of the six
    families: all but NP-04.
  * The P2 generators of NP-03, NP-18 and NP-19 had said so before any grade. One content type is left unconverted, a
    requirement's wording is not met, or the fix does not take effect in the task's environment (NP-19).
  * At iteration 0, C2 and C4 are byte copies of C1 and C3, so those audits grade the plain verifiers' own tests on the
    reference, a development candidate. C1 fails the reference in five families (all but NP-04), and C3 in four
    (NP-03, NP-05, NP-18 and NP-19). C1 and C3 are frozen as generated.
* audit:v1 requires the reference to pass, so it pulls the audited verifiers toward the reference's behaviour.
  * Several revisers relaxed checks the reference fails, for example to accept unconverted parts (NP-18) or a missing
    return value (NP-20). C2 and C4 can then accept what the contract rules out.
  * The audit's design (D24, D27) holds the reference to be valid. Where a natural reference and its contract
    disagree, the audit settles the question for the reference.
* Five audits still fail after three revisions.
  * In three (NP-04 C2, NP-05 C2 and C4), a development attack or alternative cannot be told apart from the
    reference on the requirement it targets, by the revisers' account. The attack's construction label is then in
    doubt.
  * In two (NP-03 C4, NP-19 C4) the reference still fails.
* The pre-send hash check of D65 refused one prompt: NP-03's reference-contract prompt, which the coordinator returned
  with an added newline. The coordinator resent it exactly. No unverified prompt reached an agent.
* What these mean for the run: where the reference fails its own contract, the reference checks of P5 may be unusable
  as D64 defines it, and D19's labels for that family would then be ambiguous. The source-evidence label of the
  pre-review state does not depend on them (§15.6). The run reports each family as a case study, with these facts
  beside its numbers.

### D71. Protocol v0.12 (§20): the natural arm's runs by sample, hashed before any natural held-out candidate exists
`experiments/protocol.md` with §20 appended has sha256 `cc53d24fec68888096dfb8a8bc6d7394d6dd4e707d25f13619f88e326f547068` (computed at 2026-11-22T23:34:57Z).
* **The owner's instruction.** Asked whether to amend §19's stopping rule so that the paper could report the first
  sample's natural families before the extension is built, and given the cost of each path, the owner replied: "keep
  goign until you achieve that". The build session takes this as approval of the recommended path, including the
  amendment.
* **State when it was fixed.** P1 to P4 had run for the six families (D70). No P5, P6 or P7 step had run, no natural
  held-out candidate existed, and no natural verifier had been graded on any candidate except the development ones of
  the audit loops.
* **What §20 changes.** `natural-pr-v1` grades the first sample's six accepted families once their recipe is complete.
  `natural-pr-v2` grades the extension's accepted families after their S10 and building, with the same recipe. Each
  run is reported on its own, `natural-pr-v1` as case studies (§19.6). A combined report applies the size rule to
  their union.
* **To do before the run.** The pre-flight still implements §19.5 and §19.7 for a single run `natural-pr-v1` over both
  samples. It is to implement §20.2 before `natural-pr-v1` is graded, with tests, in an entry of its own.

### D72. Round 6 to the held-out pools: P5 and P6 of four families, and the deviations found on the way
Round 6 began at 2026-11-22T23:35Z under the owner's instruction of D71. The machine restarted at 23:38Z, and the
build session started Docker as in D68. Times are UTC, 2026-11-23 unless stated.
* **P5 (F6) for NP-03, NP-04, NP-18 and NP-20.** NP-05 and NP-19 are still in their P5 fix rounds and come in a later
  entry. Every reference-check writer, reviewer and labeler prompt passed the pre-send hash check.

  | Family | Reference checks | Review | Labeler |
  | --- | --- | --- | --- |
  | NP-03 | 19 checks, usable, frozen 00:42:55 | 1 review, ok, 2 coverage remarks (R2, R5) | unusable after its one revision |
  | NP-04 | 18 checks, usable, frozen 00:22:43 | 1 review, ok | 9 checks, usable |
  | NP-18 | 14 checks, usable, frozen 00:38:23 | 1 review, ok, 1 coverage remark (R4) | 10 checks, usable at round 1 |
  | NP-20 | 20 checks, usable, frozen 00:29:01 | 1 review, ok, 1 coverage remark (R11) | usable after its revision |

  * NP-03's labeler fails on the reference: 6 of its 17 checks are string-input observables that the reference does
    not meet. Its writer, the reviewer and the revision report the same gap in the library's phrase dictionary. It is
    left out of the second labeling (§15.5). The reference-check writer found that the reference cannot meet three
    observables of the reference contract (R1, R8, R9), and its checks hold for any segmentation there. Nothing was
    regenerated because of these outcomes.
  * NP-20's labeler missed R15 as written; its revision detects all nine change requirements.
  * The reviews' coverage remarks came with an ok verdict, so no fix round ran (D33). They are reported with each
    family.
* **Order (F7).** Each family's P5 line was pushed before its P6 began: `72f5735` (NP-04), `33f50d4` (NP-20),
  `0dc21a6` (NP-18) and `98f4c44` (NP-03). Every pool generation's started_at is later than every verifier's frozen_at
  of its family, checked per run at registration.
* **P6 (the held-out pools).** NP-03, NP-18 and NP-20 each have two alternatives and three near misses. Each near miss
  names its target as the requirement it violates: NP-03 R8, R9, R1; NP-18 R2, R3, R1; NP-20 R5, R6, R1. NP-04 has
  eval-alt-1 and near misses for R4, R5 and R1; its eval-alt-2 is registered by the step below.
* **A transcript that the tools could not read.** NP-04's eval-alt-2 transcript holds raw U+2028 characters inside JSON
  strings, which JSON allows. `scripts/agent_run_record.py` split transcripts with `str.splitlines()`, which also
  splits there, and refused it. Its coordinator stopped, as the recipe requires. Every reader of JSON Lines had the same
  flaw, the natural sanitiser among them; they now split at line feeds only (`4e0776c`). No recorded output changes:
  no JSON file in the repository's data holds such a character. Of the 246 natural transcripts, only that run's and
  its registering coordinator's do.
* **Finishing a stopped registration.** A resumed workflow run would not replay the phase from cache: the coordinators'
  rules changed after NP-04's P6 began (below), so its first call would not match, and its generators would run again.
  `natural_phase.js` gains `host_step` (`0ad0a0a`): one host step on its own, with the phase's coordinator rules, and
  no generator. It is used once, to register NP-04's eval-alt-2 exactly as P6's registration says. The generator is
  not re-run.
* **Task titles in natural agents' contexts (a deviation from D65).** The harness shows the shared task list, titles
  included, to every subagent in a reminder; no agent needs to call a task tool. Agents of the build session's tooling
  workflow created two sets of five tasks:
  * Set A existed from 2026-11-22T23:43:39 to 00:28:00. Its titles named the paper's natural-run tables (for example
    "Implement make_tables.py --natural-run RUN_DIR").
  * Set B existed from 00:54:31 to 01:16:40. Its titles named review fixes (for example "L4-L6: B1 partial norm,
    infrastructure disclosure, refcheck status record").
  * 19 natural generator runs had set A in their context: 6 reference-check writers, 5 labelers, 3 labeler revisions
    and 5 reviews. 23 had set B: 8 alternatives, 11 near misses, 2 reference-check fix rounds and 2 reviews. 13 host
    coordinators had one of the sets. No run of P1 to P4 had a task list in its context.
  * No title names a family, a requirement, a check, a target, a label or a candidate. The build session searched each
    exposed run's own text and tool inputs for 25 distinctive terms of the titles and found none in any of the 42 runs.
  * Builder decision, pending the owner's review: nothing is regenerated for this, and the exposed runs are kept. The
    titles carried no information about any task, and no run shows a trace of them. The deviation is reported with
    the natural results.
  * Remedies: the build session deleted both sets and stopped the tooling workflow; it then finished that workflow's
    last verification itself. The coordinators' rules now forbid the task-list tools (`8796802`). The build session
    gives its own workflows the same rule while natural agents run, and checks the list is empty before launching a
    natural phase.
* **Scanner.** A natural verifier splits the study's own sandbox idiom over two lines, so the head of the call
  (`r = run_python(_snippet(`) became a natural code line. It matched the controlled runs' results 138 times and
  blocked a push. A natural line that a line of the pre-natural corpus holds within it is now an idiom too, with the
  same word-boundary rule as the search (`dc055b2`). Of 34,354 natural code lines, 18 are newly left out: imports, call
  heads and other idioms of the study's own code and the standard library. No finding is suppressed and nothing is
  listed by name.
* **NP-03's host log** quoted a two-character test input that may be thread text, in one entry. The build session
  replaced it with a placeholder and logged the redaction, as for NP-19 (D65).
* **The strict re-audit (D44)** of every natural family's audit file is the builder's. It runs after all six P7s.

### D73. The pre-flight implements §20.2; D19's labels for `natural-pr-v1` are the run's first step
* **The pre-flight (`f943d1b`), as D71 asks.**
  * It knows two natural runs: `natural-pr-v1` for the first sample and `natural-pr-v2` for the extension. A natural
    run with no run id or another id is refused, citing §20.2.
  * `natural-pr-v1`: building has stopped once S9 is complete for the first sample and no first-sample family or
    reserve in a repository with an open place lacks an S10 outcome. There is no 30-accepted branch, as §20.2 says.
  * `natural-pr-v2`: 30 accepted tasks in all, or the extension's S9 record complete with no extension family pending.
  * A run that includes a family of the other sample, leaves out an accepted family of its own, or meets an index row
    that names neither sample, is refused.
  * Readings chosen: a repository's open places are counted over both samples, because the cap of §15.6 and §19.3
    applies to both together. Only the run's own sample's rows need an S10 outcome. The stricter reading would block
    `natural-pr-v1` for good once an extension family filled a first-sample repository; on the committed index both
    readings agree.
* **When D19 runs.** D19 grades the frozen reference checks and the regression norm on every held-out candidate.
  §20.2 says that no natural verifier is graded on a held-out candidate of a family before that family's run. Under
  §19.7, `propose_labels.py` read the same rule as "not before building has stopped" and ran D19 as the first step of
  the run.
  * The build session applies that reading per sample: D19 for `natural-pr-v1` runs once building has stopped for the
    first sample and each of the six families' seven phase-end lines is committed. It is the run's first step, followed
    by the pre-flight and the grading.
  * By then every verifier, contract and candidate of the six is frozen or registered. No D19 grade changes any of them.
  * This is a builder reading, pending the owner's review.
* **To do before D19, with tests.**
  * `propose_labels.py` takes the family's sample from its committed index row and applies the per-sample rule. Until
    now it applied the rule for both samples, which refuses the six until the extension is built.
  * `propose_labels.py`, and the pre-flight for every family of a natural run, require the family's P1 to P7 lines in
    the committed phase-end log.
  * The natural index is committed again after the last P7 (D65).

### D74. When D19 may run, as code: the label gate and the pre-flight read the committed records
D73 listed what was to be done before D19, with tests. It was built in an isolated worktree, reviewed through two
lenses (correctness; fidelity to the protocol and this log), fixed, and verified again by the build session. This
entry records it before its first use.
* **The label gate (`scripts/propose_labels.py`).** D19 runs on a natural family only when all of these hold, by the
  records as the HEAD commit holds them:
  * the family's row in the committed natural index names its sample;
  * building has stopped for that sample (the pre-flight's rule of §20.2, D73);
  * the family is accepted (S11);
  * every row of the index names a sample;
  * the committed phase-end log holds P1 to P7 of the family and of every accepted family of its sample, the families
    its run grades with it.

  Anything that cannot be read or applied is a refusal, before anything is looked up, graded or written. The rules are
  the pre-flight's own functions, so the gate and the pre-flight cannot disagree on these records.
* **The pre-flight** requires the same seven phase-end lines for every natural family a run grades.
  * The log is read from HEAD, never from the working tree. One malformed line makes it unusable.
  * "In order" means, in the log's order, each phase once, after the one before it, with a `recorded_at` no earlier.
    The time condition is the pre-flight's own reading; D65 names the log's commits as the order record, and those stay
    the builder's record.
  * Two shared rules now fail closed:
    * a family that the S9 record lists for a sample must have a row naming that sample;
    * a row that names no sample counts for both samples.
* **`scripts/record_phase_end.py`** refuses to append a line that the reader would refuse later: a time earlier than
  the family's last, a time without a time zone, and a log line that is not a JSON object.
* **The reviews.**
  * Both reviewers found that the first version required only the family's own phase ends, where D73 requires every
    family of its run.
  * One found that a row naming no sample could hide a family from the building rule.
  * Ten findings in all were confirmed and fixed. The build session added the S11 requirement, which neither review
    raised.
  * Each new or changed test fails without its change. Full offline suite, ruff (no new finding) and
    `verify_frozen_inputs` are as the commit says.
* **Effect now.** D19 and the pre-flight refuse every first-sample family until all six have committed their P7 line.
  This is the order D73 describes.

### D75. Construction closes for the first sample: P5 to P7 of all six families, the audits, and what runs did outside the recipe
Times are UTC, 2026-11-23. This continues D72.
* **P5 of NP-05 and NP-19.**

  | Family | Reference checks | Review loop | Labeler |
  | --- | --- | --- | --- |
  | NP-05 | 18 checks, usable, frozen 01:50:57 | 2 fix rounds; the third review says needs_fix (8 issues, recorded only, D33) | 17 checks, usable after its revision |
  | NP-19 | 10 checks, usable, frozen 02:03:42 | 1 fix round; the second review ok, 1 coverage remark (R1) | unusable after its revision |

  NP-19's labeler fails on the reference: three of its R1 checks fail there, and its R4 checks pass on the no-op. It is
  left out of the second labeling (§15.5), as NP-03's is (D72). So two of the six families have no second labeling.
* **P6 of NP-05 and NP-19.** Each has two alternatives and three near misses, every one generated after its family's
  last freeze (F7). Each near miss names its own target: NP-05 R8, R7, R1; NP-19 R4, R3, R1.
  * NP-05's eval-nm-3 adds that a strict reader could also count it against R8.
  * NP-19's near-miss writers report that the reference's fallback compares an error text case-sensitively, so the
    reference fails R1 in their mocked setups. NP-19's frozen reference checks pass the reference in all three repeats.
  * These remarks are recorded with the families. They change no label: D19 decides the labels.
* **P7 of all six.** Two mappers each; their files were copied byte for byte, with no correction. No family has a
  same-code duplicate. In NP-19 both mappers agree, and neither contract covers reference R4.
* **The audits.** Each natural agent's transcript was audited with the natural-agent profile, and each flag was read in
  its transcript and assessed.

  | Family | Records | Flagged | Hits | Exposures |
  | --- | --- | --- | --- | --- |
  | NP-03 | 29 | 17 | 52 | 11 |
  | NP-04 | 24 | 13 | 47 | 10 |
  | NP-05 | 34 | 19 | 124 | 21 |
  | NP-18 | 23 | 17 | 69 | 34 |
  | NP-19 | 30 | 27 | 161 | 105 |
  | NP-20 | 23 | 14 | 125 | 29 |

  No record is excluded. Of the 578 hits:
  * 452 are inside forbidden material, as the profile resolves paths:
    * 420 are tokens of the agents' commands, or relative paths in the agent's own repository copy, resolved under
      the study's repository. 15 of these look like the study's `src/` or `docs/` but are the natural repository's own
      paths.
    * 28 are relative paths resolved into the family's workspace root.
    * 4 use the study's environment: three existence checks of the CLI that the prompt names, and one use of its Python
      to parse the agent's own test file.
  * 66 are host Python code that names a network module, mostly snippets that parse or compile the agent's own test
    file. The assessments record no network use.
  * 23 are container-engine calls made directly (below).
  * 17 are outside the agent's workspace, 17 are a Claude session directory (the harness's copy of a saved tool
    output), and 3 are CLI calls outside the allowlist.
* **The strict re-audit (D44).** It applied the same profile and found the same hits and exposures as the P7 audit in
  all 163 records. Each record's assessment therefore applies, and the build session wrote that into the record's block.
* **What runs did outside the recipe.** Each was assessed as not excluded and is disclosed with its family.
  * Three runs started the task image with `docker run` themselves instead of through the workspace wrappers: NP-03
    eval-nm-3, NP-04 refcheck-review-1 and NP-19 refcheck-fix-1.
    * Each used `--network none`, its own read-only repository, and the wrappers' isolation options.
    * Five other runs queried the container engine read-only (images, processes).
    * NP-04's review verdict rests partly on its own runs.
    * The audit missed one of NP-04's calls. Both audits use the same profile, so the strict re-audit missed it too.
      That gap is noted here, not fixed mid-audit.
  * Four runs wrote temporary files outside their workspaces, against their templates:
    * NP-04 eval-alt-1 wrote and ran a mutation-check helper in the build session's scratch directory. The build
      session moved the helper into the family's private run records.
    * NP-05's labeler made a stub module there and then removed the directory with `rm -rf`. That also removed a stale
      stub of the controlled arm's tooling (2026-11-13 and 11-18), whose content is in those agents' transcripts.
    * NP-19's diff-derived writer wrote an empty file there and removed it.
    * NP-20's freeform verifier writer wrote stderr files to the host's `/tmp`.

    The cause is the harness: it gives every subagent the session's scratch directory as the place for temporary
    files. By the audits, none of these runs read the build session's files there.
  * NP-05's mappers map an initial-only requirement to an explicit but unscored reference requirement. They also name a
    contradiction with an unresolved, unscored one. Coverage counts scored requirements only, so neither changes a
    number.
* **The index after P7** (`4dae422`, D65). Only the six families' rows change: their file hashes and their candidates.
  It was written from the first sample's task directories, so the ten directories left by the extension's stopped
  S10 step are not recorded, as D66 decided. Those directories hold S10 outcomes that the stopped step wrote after the
  usage limit, and they are to be built again from the start.
* **Next (D73, D74).** D19 runs on the six families as the first step of `natural-pr-v1`. Then come the pre-flight and
  the run, with `--pilot`: every family's acceptance gate is pending, because provenance eligibility needs a human
  reviewer (§16.4). The manifest records the pilot flag.
