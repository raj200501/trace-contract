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
