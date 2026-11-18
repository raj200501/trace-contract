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
