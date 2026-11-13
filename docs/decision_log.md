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
