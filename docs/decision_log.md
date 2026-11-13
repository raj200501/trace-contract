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

### D6. CS-01 initial-state approximation
humanize generates `src/humanize/_version.py` at build time (hatch-vcs). The build
backend is not run on the host; a fixed `_version.py` is added to the workspace and
recorded as a snapshot approximation (`fidelity = approximate`). The file is
gitignored upstream, so it does not appear in candidate diffs.
