# Harbor 0.25.0 integration spec (TraceContract)

Cluster: exact, version-pinned Harbor integration spec, for the TraceContract (working name) project.
Access date for every source below: **2026-11-13 (UTC)**. Publication/version dates are recorded separately.
No commits were made as part of this research step. No files under `/home/user/trace-contract` were modified except this notes file.

Conventions in this file:
- "States:" / a quotation / "code:" means the source says it (code path:line or doc section given). "Probe:" / "My check:" / "Inference:" means my own reasoning or an experiment I ran, not a Harbor claim.
- `INST` = the INSTALLED 0.25.0 package `…/scratchpad/harbor-venv/.venv/lib/python3.13/site-packages/harbor`. All API facts and path:line references are from INST unless prefixed `MAIN`.
- `MAIN` = the clone `/home/user/harbor-framework/harbor` at `main @ 3bf4cb308b886d41c0151a21e7c3b6ec8cb68f07` (committed 2026-11-12), which is **ahead** of 0.25.0. MAIN differences are flagged explicitly in §9.
- Short quotes are verbatim, at most 2 sentences, with the file/section they come from.

---

## 0. Bibliographic / provenance record

| Field | Value | Where verified |
|---|---|---|
| Package | PyPI `harbor` **0.25.0** | `INST` `importlib.metadata.version('harbor')` prints `0.25.0`; `harbor --version` prints `0.25.0` |
| Release date of 0.25.0 | **2026-10-25** (wheel upload 2026-10-25T20:27:25Z) | `pypi.org/pypi/harbor/0.25.0/json` |
| Requires Python | `>=3.12` (venv runs 3.13) | PyPI `info.requires_python` |
| License | **Apache-2.0** | `MAIN/LICENSE` header; `MAIN/CITATION.cff` `license: Apache-2.0` |
| Repo | `github.com/harbor-framework/harbor` | `INST/constants.py:10` DEFAULT_REGISTRY_URL `raw.githubusercontent.com/laude-institute/harbor/main/registry.json`; CITATION repository-code `github.com/harbor-framework/harbor` |
| Docs site | `https://docs.harborframework.com` (Mintlify) | fetched 2026-11-13 |
| Citation / DOI | "Harbor: A framework for evaluating and optimizing agents and models in container environments", Harbor Framework Team, v0.25.0, 2026-10-25, DOI 10.5281/zenodo.20953922 | `MAIN/CITATION.cff` |
| ATIF spec | RFC 0001, Status Active, Maintainer "Boxuan Li", Date "April 2026", Changelog v1.8 | `MAIN/rfcs/0001-trajectory-format.md` header |
| Clone commit | `main @ 3bf4cb308b886d41c0151a21e7c3b6ec8cb68f07` (feat(server): upload jobs to Harbor Hub (#4278), 2026-11-12 15:32 -0800) | `git log -1` |

Local host for probes: Docker Engine **29.9.2**, Compose **v5.6.1**, daemon OSType `linux`, **rootless** (`docker info` SecurityOptions include `name=rootless`... actually `rootless` appears in SecurityOptions), kernel `6.18.44-fc-v445`. Docker image pulls worked for `python:3.12-slim` (pinned digest `sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`). `registry-1.docker.io` returned HTTP 429 on the Harbor egress-probe alpine digest during one probe, so the nftables kernel probe (§7) could not be run end-to-end; recorded as not-attempted.

---

## 1. Sources consulted

| # | Source | URL / path | Kind | Version / pub date | Full text read? | Notes |
|---|---|---|---|---|---|---|
| 1 | Installed `harbor` package source | `INST/...` | primary code | 0.25.0 (2026-10-25) | key modules in full | authoritative for API facts |
| 2 | Harbor clone (main) | `/home/user/harbor-framework/harbor` | primary code | main@3bf4cb3 (2026-11-12) | diffed vs INST | ahead of 0.25.0; see §9 |
| 3 | Tasks → Overview | docs.harborframework.com/tasks/overview | docs | fetched 2026-11-13 | yes | task dir layout |
| 4 | Tasks → Separate verifier | .../tasks/separate-verifier | docs | 2026-11-13 | yes | artifact transfer, image selection, sanitization |
| 5 | Tasks → Configuration | .../tasks/configuration | docs | 2026-11-13 | yes | full task.toml field reference |
| 6 | Tasks → Verifier | .../tasks/verifier | docs | 2026-11-13 | yes | reward files |
| 7 | Tasks → Solution | .../tasks/solution | docs | 2026-11-13 | yes | oracle solution |
| 8 | Tasks → Network policies | .../tasks/network-policies | docs | 2026-11-13 | yes | modes, phases, provider grid |
| 9 | Tasks → Artifacts / Environment / Resources / Instruction / Lint / Multi-step | .../tasks/* | docs | 2026-11-13 | yes | — |
| 10 | Jobs → Error classification | .../jobs/error-classification | docs | 2026-11-13 | yes | **describes MAIN semantics (should_retry/should_grade/has_valid_reward), NOT 0.25.0** — see §4, §9 |
| 11 | Jobs → Regrade / Custom verifiers / Artifact collection | .../jobs/* | docs | 2026-11-13 | yes | — |
| 12 | Agents → ATIF | .../agents/atif | docs | 2026-11-13 | yes | — |
| 13 | ATIF RFC 0001 | `MAIN/rfcs/0001-trajectory-format.md` | primary spec | v1.8 (Apr 2026) | relevant sections | — |
| 14 | CLI `--help` outputs | captured to `…/harbor_probe/help/*.txt` | primary | 0.25.0 | yes | task/run/trial/lint/check/init/exec/agent/job etc. |
| 15 | My toy task + runs | `…/harbor_probe/` | my experiment | 2026-11-13 | — | §8 (validated) |

---

## 2. Task directory layout and task.toml field reference

### 2.1 Directory layout (code: `INST/models/task/paths.py` docstring, lines 14-31; `INST/models/task/task.py:34-48`)

```
my-task/
├── instruction.md          # single-step instruction (markdown), task root
├── trajectory.json         # OPTIONAL ATIF prior context seeded before the agent runs (TaskPaths.TRAJECTORY_FILENAME, paths.py:39)
├── task.toml               # TaskPaths.CONFIG_FILENAME (paths.py:34)
├── environment/
│   └── Dockerfile | docker-compose.yaml | singularity-compose.yaml | ...
├── solution/               # copied to container @ /solution by OracleAgent
│   └── solve.{sh,bat}      # + any supporting files
└── tests/                  # copied to container @ /tests by the Verifier (shared mode) or baked into verifier image (separate)
    └── test.{sh,bat}       # + any supporting files
```
Multi-step adds `steps/<step-name>/{instruction.md, tests/, solution/, workdir/setup.sh, trajectory.json}` and an optional base `tests/` fallback (docs §tasks/overview; `paths.py:160-235`). Linux uses `.sh`, Windows uses `.bat`; discovery is OS-filtered (`INST/utils/scripts.py:86-114`, `discover_script`). `.harborignore` inside `tests/` or `solution/` (and step equivalents) excludes local helper files from sandbox uploads, publication, and content hashes (docs §tasks/overview "Local development files"). **The `trajectory.json` beside the instruction is the hook TraceContract can use to ship prior agent context** (see §5.3, §6).

### 2.2 task.toml schema — the Pydantic models are authoritative

`TaskConfig` is the root (`INST/models/task/config.py:853-877`). Top-of-file note (config.py:1-2): "When updating this file, also update the corresponding docs page: docs-mintlify/tasks/configuration.mdx" — so the docs track the model.

Root fields (`TaskConfig`, config.py:853-878):
- `schema_version: str = "1.4"` (config.py:854). Legacy `version` key is remapped to `schema_version` (config.py:896-901).
- `task: PackageInfo | None = None` (config.py:855) — `[task]` registry metadata. `PackageInfo` (config.py:289): `name` (required, `org/name` format, validator config.py:317-326), `version: str | None`, `description: str = ""`, `authors: list[Author]`, `keywords`.
- `metadata: dict[str, Any] = {}` (config.py:859) — **arbitrary; accepts any keys** (this is where TraceContract provenance/requirement metadata can live in task.toml; `unknown-config-field` lint does NOT descend into `metadata` — confirmed in §8, my task put `tracecontract_*` tables under `[metadata]` and lint passed with `--extend-select ALL`).
- `verifier: VerifierConfig` (config.py:860), `agent: AgentConfig` (config.py:861), `environment: EnvironmentConfig` (config.py:862), `solution: SolutionConfig` (config.py:863).
- `source: str | None` (config.py:864) — provenance string.
- `multi_step_reward_strategy: "mean" | "final" | None` (config.py:865).
- `steps: list[StepConfig] | None` (config.py:877).
- `artifacts: list[str | ArtifactConfig] = []` (config.py:878).

`EnvironmentConfig` (task-side, config.py:435-490), relevant fields and defaults:
- `build_timeout_sec: float = 600.0`; `docker_image: str | None = None` (if set, `environment/` optional); `os: TaskOS = "linux"` (`"linux"|"windows"`, config.py:275-279).
- Resources: `cpus: int|float|None`, `memory_mb: int|None`, `storage_mb: int|None`, `gpus: int|None`, `gpu_types: list[str]|None`, `tpu: TpuSpec|None` (type+topology, config.py:382-422).
- `network_mode: NetworkMode = "public"` (via `BaselineNetworkPolicyConfig`, config.py:253) + `allowed_hosts: list[str] | None`. `NetworkMode` = `no-network | public | allowlist` (config.py:40-45).
- `mcp_servers: list[MCPServerConfig] = []` (config.py:463; `MCPServerConfig` config.py:635-680: name, transport `stdio|sse|streamable-http`, url, command, args, headers — credential headers must be `${VAR}` without default, config.py:660-664).
- `env: dict[str,str] = {}` (config.py:464) — `${VAR}` / `${VAR:-default}` host templating.
- `skills_dir: str | None`; `healthcheck: HealthcheckConfig | None` (config.py:351-379: command, interval_sec=5, timeout_sec=30, start_period_sec=0, start_interval_sec=5, retries=3); `workdir: str | None`.
- `allow_internet: bool | None` — **deprecated**, mapped to network_mode (config.py:484-490, 924-942).

`AgentConfig` (task-side, config.py:343-348): `timeout_sec: float | None = None`; `user: str | int | None = None` ("None uses the environment's default USER (e.g., root)") + inherited phase `network_mode`/`allowed_hosts` overrides (applied during `agent.run()` only).

`VerifierConfig` (task-side, config.py:580-629):
- `timeout_sec: float = 600.0`; `env: dict[str,str]`; `user: str|int|None`.
- `environment_mode: "shared" | "separate" | None` (config.py:587). **Resolution** (`INST/models/task/verifier_mode.py:15-45`): explicit mode wins; else a `[verifier.environment]` implies `separate`; else `shared`. `shared` + `[verifier.environment]` is a validation error (config.py:618-629).
- `environment: EnvironmentConfig | None` — separate-verifier container, same schema as `[environment]`.
- `collect: list[VerifierCollectConfig]` (config.py:608) — commands run in compose services after the agent phase, before artifact collection (config.py:778-809): command, service=main, timeout_sec=60, user.
- phase `network_mode`/`allowed_hosts` override during `verify()`.

`SolutionConfig` (config.py:339-340): `env: dict[str,str] = {}` only (applied when the Oracle runs `solve.sh`).

`ArtifactConfig` (config.py:692-775): `source` (container path; `..` rejected, config.py:713-725), `destination: str | None` (host-relative; absolute/`..`/`manifest.json` rejected, config.py:727-763), `exclude: list[str]`, `service: str | None` (compose service; non-main requires absolute source, config.py:765-775).

`StepConfig` (config.py:812-843): `name`, `agent`, `verifier`, `min_reward: float | dict[str,float] | None` (gates remaining steps; missing verifier_result or gated key treated as `-inf`, config.py:816-824), `healthcheck`, `artifacts`.

JSON Schema is dumpable: `harbor task schema` / `harbor trial schema` (captured; `$defs` include AgentConfig, ArtifactConfig, Author, EnvironmentConfig, HealthcheckConfig, MCPServerConfig, NetworkMode, PackageInfo, SolutionConfig, StepConfig, TaskOS, TpuSpec, VerifierCollectConfig, VerifierConfig, VerifierEnvironmentMode).

### 2.3 Special container paths (code: `INST/models/trial/paths.py:39-48` `EnvironmentPaths`)

| Container path | Meaning | Host mount (local docker, when auto_mounting) |
|---|---|---|
| `/logs/verifier/` | verifier working dir; **reward + verifier output** | `<trial>/verifier/` |
| `/logs/verifier/reward.txt` | single float reward | `<trial>/verifier/reward.txt` |
| `/logs/verifier/reward.json` | labeled numeric rewards `{key: number}` | `<trial>/verifier/reward.json` |
| `/logs/agent/` | agent logs (and `trajectory.json`) | `<trial>/agent/` |
| `/logs/user-agent/` | simulated-user logs (only if `user_agent` set) | `<trial>/user-agent/` |
| `/logs/artifacts/` | agent "convention" publish dir, auto-collected | `<trial>/artifacts/logs/artifacts/` |
| `/solution/` | Oracle copies `solution/` here | (copied, not mounted) |
| `/tests/` | shared-verifier tests uploaded here; bundled in image for separate | (copied/baked) |
| `/runtime/skills` | default injected-skills dir (`default_skills_dir`, paths.py:46) | — |

Windows: `C:/` prefixed equivalents (`EnvironmentPaths.for_windows`, paths.py:51-81).

---

## 3. Trial output layout and result files

Host trial dir (`INST/models/trial/paths.py:84-146` `TrialPaths` docstring, confirmed by my runs in §8):
```
trial_dir/
├── agent/          # agent logs (trajectory.json, oracle.txt for oracle, exit-code.txt on nonzero)
├── user-agent/     # only for simulated-user trials
├── verifier/       # test-stdout.txt, reward.txt|reward.json, any files the test writes
├── artifacts/      # collected artifacts + manifest.json
│   ├── manifest.json
│   └── <mirrored source paths / destinations>
├── config.json     # TrialConfig as written (see §3.2)
├── lock.json       # resolved replayable inputs (TrialLock)
├── result.json     # TrialResult  <-- primary machine-readable outcome
├── exception.txt   # full traceback, only when the trial raised (trial.py:678)
└── trial.log       # trial logger output
```
Property names: `TrialPaths.result_path` -> `result.json` (paths.py:289-291), `config_path` -> `config.json`, `lock_path` -> `lock.json`, `reward_text_path`/`reward_json_path` (paths.py:273-286), `test_stdout_path` -> `verifier/test-stdout.txt` (paths.py:260), `exception_message_path` -> `exception.txt` (paths.py:293-298), `log_path` -> `trial.log`.

Multi-step relocates `agent/ verifier/ artifacts/` into `steps/<name>/` after each step (paths.py:109-126).

### 3.1 `result.json` = `TrialResult` (code: `INST/models/trial/result.py:75-102`)

Key fields (0.25.0): `id: UUID`, `task_name`, `trial_name`, `trial_uri`, `task_id`, `source: str|None`, `task_checksum`, `config: TrialConfig`, `agent_info: AgentInfo`, `agent_result: AgentContext|None`, **`verifier_result: VerifierResult|None`**, `verifier_environment_mode: "shared"|"separate"|None` (None for multi-step, result.py:87-94), `exception_info: ExceptionInfo|None`, timing (`started_at`, `finished_at`, `environment_setup`, `agent_setup`, `agent_execution`, `verifier` as `TimingInfo{started_at,finished_at}`), `step_results: list[StepResult]|None`.

`VerifierResult` (code: `INST/models/verifier/result.py:4-5`) is just:
```python
class VerifierResult(BaseModel):
    rewards: dict[str, float | int] | None = None
```
So `result_json["verifier_result"]["rewards"]` is a flat `{label: number}` map, or `verifier_result` is `null` when verification failed/was skipped. My reference run: `"verifier_result": {"rewards": {"reward": 1, "R1": 1, "R2": 1}}`.

`ExceptionInfo` (result.py:22-41, 0.25.0): `exception_type` (the Python class name, e.g. `"RewardFileNotFoundError"`), `exception_message`, `exception_traceback`, `occurred_at`. `.policy` property -> `ErrorPolicy` via `policy_for(exception_type)` (see §4). `TrialResult.reward_valid` property (result.py:122-128): `False` if no rewards; else `True` only if every recorded exception's `policy.reward_valid` is True.

### 3.2 `config.json` vs `lock.json`

- `config.json` = `TrialConfig.model_dump_json(exclude_defaults=True)` in 0.25.0 (trial.py:1182-1184) — only non-default fields; my minimal run wrote just `task.path`, `trial_name`, `trials_dir`. (MAIN removed `exclude_defaults`; see §9.)
- `lock.json` = `TrialLock` (`build_trial_lock`), `schema_version: 2`, records the task **content digest** (`task.digest = sha256:...`), agent, environment, verifier, and for regrades the nested `source_trial` with the source task digest. This is the durable replay record and the field to use for task-content identity (Task.checksum is deprecated: task.py:244-268).

---

## 4. How the verifier runs; reward read/write; error representation

### 4.1 Default `Verifier.verify()` (code: `INST/verifier/verifier.py:198-310`)

Sequence per verify pass:
1. Resolve test script for the env OS (`_resolve_tests`, verifier.py:126-165). If `skip_tests_upload` (dedicated verifier image bundles tests), nothing is uploaded.
2. **`_remove_reward_files()` (verifier.py:167-195): deletes `/logs/verifier/reward.txt` and `reward.json` inside the container as user `root` before running the test** (`rm -f -- ...`). So a reward file planted during the agent phase or baked into the image is cleared first. Raises `RuntimeError` if the `rm` exits nonzero.
3. Upload `tests/` to `/tests/` (shared/fallback only), merge env (`task.config.verifier.env` < `verifier_env` < `override_env`), `chmod +x` the test script if `.sh`, then `exec` the test with stdout+stderr redirected to `/logs/verifier/test-stdout.txt` (`build_execution_command`, scripts.py:122-160: `(cmd) > <stdout> 2>&1`).
4. The test runs as **`environment.default_user`**, which the caller sets to the effective verifier user (`step.verifier.user` or `task.config.verifier.user`; None => container default, typically root) (verifier.py:267-272; trial.py `_run_shared_verifier`/`_run_separate_verifier` wrap in `with ...with_default_user(user)`).
5. Download `/logs/verifier/` to host (unless mounted).
6. **Reward precedence: `reward.json` wins over `reward.txt`** (verifier.py:299-303).

Reward parsing (strict):
- `.txt` (`_parse_reward_text`, verifier.py:69-89): empty -> `RewardFileEmptyError`; non-float -> `VerifierOutputParseError`; non-finite (NaN/Inf) -> `VerifierOutputParseError`; else `{"reward": <float>}`.
- `.json` (`_parse_reward_json`, verifier.py:91-124): empty -> `RewardFileEmptyError`; invalid JSON -> `VerifierOutputParseError`; any value not `int|float`, or non-finite -> `VerifierOutputParseError`; else the dict is returned **verbatim as the rewards map** (so `{"reward":1,"R1":1,"R2":0}` is preserved; label keys are arbitrary).
- Neither file -> `RewardFileNotFoundError`.
- If `reward.json` is a bare JSON number `1` (not an object), parsing returns `1`, then `VerifierResult(rewards=1)` raises pydantic `ValidationError` (`rewards` must be a dict) — confirmed in §8.

### 4.2 How errors / timeouts / crashes / missing reward are represented (PROBED, 0.25.0)

My toy verifier had probe `MODE`s; results from `result.json.exception_info` (separate-verifier, docker). **This is 0.25.0 behavior:**

| Probe | `exception_info.exception_type` | `verifier_result` | Reward files on host |
|---|---|---|---|
| test exits nonzero, no reward file (`crash`) | `RewardFileNotFoundError` | `null` | none written |
| reward.txt = `not-a-number` (`garbage`) | `VerifierOutputParseError` | `null` | reward.txt present but unparsed |
| reward.txt empty (`empty`) | `RewardFileEmptyError` | `null` | empty reward.txt |
| reward.json = `{"reward":"yes"}` (`json_string`) | `VerifierOutputParseError` ("Non-numeric reward 'yes'") | `null` | reward.json present |
| reward.json = bare `1` (`json_number`) | `ValidationError` (rewards must be dict) | `null` | reward.json present |
| write reward then `exit 1` (`reward_then_fail`) | `null` (no error) | `{"reward":1.0}` | **test's nonzero exit is ignored; the reward file is what matters** |
| `sleep 30` with `--verifier-timeout 5` | `VerifierTimeoutError` ("Verifier execution timed out after 5.0 seconds") | `null` | — |

Key facts:
- **A crashed/timed-out/unparseable verifier yields `verifier_result = null` and a typed `exception_info`; it does NOT silently become reward 0.** The job-level aggregation in 0.25.0 only counts trials whose `verifier_result.rewards` is non-None (job.py / models/job/result.py:143-150), so a failed verify is excluded from the mean denominator rather than scored 0.
- **The test script's own exit code is not the reward.** Only the reward file is read (`reward_then_fail` above). A test can `exit 0` with a stale/missing reward and still fail, or `exit 1` after writing a valid reward and still be graded.
- "Stale" reward files are handled by step 2 above: Harbor deletes them before the test runs, so a reward written by the agent (or by a previous step in shared mode, trial.py:944-951 `_reset_shared_step_verifier_dirs`) cannot leak into the next verify.
- Exception class provenance (0.25.0): `RewardFileNotFoundError`, `RewardFileEmptyError`, `VerifierOutputParseError` are in `verifier/verifier.py:34-39`; `VerifierTimeoutError` in `trial/errors.py:12-13`; `AddTestsDirError`, `DownloadVerifierDirError` in `verifier.py:22-31`.

### 4.3 Error classification table (**0.25.0**, code: `INST/models/trial/error_policy.py`)

0.25.0 uses `ErrorPolicy(cause: FailureCause, retry: bool, grade: bool)` and a derived `reward_valid` property (error_policy.py:32-43). `reward_valid` is True only for `AGENT_EXHAUSTED_BUDGET` and `AGENT_REFUSED_TASK`. Groups (error_policy.py:50-130):
- `SANDBOX_FAILED` (retry=T, grade=F): EnvironmentStartTimeoutError, SandboxBuildFailedError, AgentSetupTimeoutError, HealthcheckError, SandboxLikelyOutOfMemoryError, MemoryLimitExceededError, SSHAccessError, GKE…, RuntimeRequestError, **AddTestsDirError, DownloadVerifierDirError**.
- `MODEL_PROVIDER_FAILED` (retry=T, grade=T): ApiError, ApiRateLimitError, … Timeout.
- `MODEL_PROVIDER_FAILED` (retry=F, grade=T): BadRequestError, …, BudgetExceededError.
- `MODEL_PROVIDER_FAILED` (retry=F, grade=F): AgentAuthenticationError, ModelNotFoundError, AuthenticationError, …
- `HARBOR_FAILED` (retry=F, grade=F): ServiceOperationsUnsupportedError, VercelScopeError, DspyImportError, MissingExtraError, RegradeError.
- `UNCLASSIFIED` (retry=T, grade=T): NonZeroAgentExitCodeError.
- `AGENT_EXHAUSTED_BUDGET` (retry=F, grade=T, **reward_valid=T**): AgentTimeoutError, ContextWindowExceededError, OutputTokenExceededError, ContextLengthExceededError, OutputLengthExceededError.
- `AGENT_REFUSED_TASK` (retry=F, grade=T, **reward_valid=T**): AgentSafetyRefusalError, ContentPolicyViolationError.
- **`VERIFIER_FAILED` (retry=F, grade=T, reward_valid=F): VerifierTimeoutError, RewardFileNotFoundError, RewardFileEmptyError, VerifierOutputParseError.**
- `CANCELLED` (retry=F, grade=F): CancelledError.
- Unlisted -> `UNKNOWN_ERROR_POLICY` (UNCLASSIFIED, retry=T, grade=T).

`default_exclude_exceptions()` (error_policy.py:141) = names with retry=False.

**CAUTION for TraceContract:** the public docs page `jobs/error-classification` describes the **MAIN** model (three independent booleans `should_retry`/`should_grade`/`has_valid_reward`, a job/trial-level `override_error_policy`, and `VerifierTimeoutError`/reward-file errors as `should_grade=True, has_valid_reward=False`). That override mechanism and field naming are **NOT in 0.25.0** (see §9). If you pin 0.25.0, do not rely on `override_error_policy`, `should_grade`, `ErrorPolicyOverride`, or the "No/Yes/No" verifier-error semantics from the docs — 0.25.0 `ValidationError` on a bare-number reward.json also classifies as UNKNOWN (retry=T, grade=T) rather than a verifier-failed cause.

Interpretation for our "false acceptance" measurement: a design where the verifier-audit step aborts without a reward (crash) is recorded as a typed verifier failure (`verifier_result=null`), which is distinguishable from a genuine reward 0. **TraceContract should score candidates on `verifier_result.rewards` and treat `verifier_result is null` as "no decision", not as rejection.**

---

## 5. Separate-verifier mode, oracle/nop agents, artifact transfer

### 5.1 Verifier environment resolution (code: `INST/models/task/verifier_mode.py:48-133`, `INST/trial/single_step.py`, `INST/trial/trial.py:1013-1134`)

- `resolve_effective_verifier_env_config`: separate mode uses, in order, `step.verifier.environment` > `task.verifier.environment` > a **fresh deep copy of `task.environment`** (verifier_mode.py:48-69).
- Image selection (verifier_mode.py:89-133, docs §tasks/separate-verifier "Image selection"): priority (1) `[verifier.environment].docker_image` (tests baked in); (2) `tests/Dockerfile` or `tests/docker-compose.yaml` (tests baked in, `bundled_tests=True`); (3) `[environment].docker_image` (tests uploaded to `/tests/`); (4) `environment/Dockerfile` (tests uploaded). `bundled_tests=True` sets `skip_tests_upload` so Harbor does NOT upload `tests/` (verifier_mode.py:106-119).
- In `SingleStepTrial._run` (single_step.py:37-54): for **separate** mode the agent env is stopped BEFORE `_run_verifier`, and artifacts are collected with `stop_main_before_sidecars=True`. For **shared** mode the agent env is stopped after verification.
- Separate verifier env is a fresh container (`_separate_verifier_env`, trial.py:1083-1134) with its own session id `{trial_name}__verifier__{key}`, started with `extra_docker_compose` cleared (trial.py:1092-1094) — **runtime mounts and compose overlays are NOT propagated to the separate verifier** (`check_trial_config` warns, trial.py:107-134; docs §jobs/artifact-collection warning).

### 5.2 Artifact transfer into the separate verifier (code: `INST/trial/artifact_handler.py`, `INST/environments/tar_transfer.py`)

**What is transferred automatically:** only (a) the agent convention dir `/logs/artifacts/` and (b) every path listed in task/trial/step `artifacts` (docs §tasks/separate-verifier "Artifact transfer"; §tasks/artifacts). `/logs/agent/` and `/logs/verifier/` are NOT copied unless declared as artifacts (e.g. `artifacts = ["/logs/agent/trajectory.json"]` for trajectory grading).

**Placement:** each artifact is re-materialized at its **original container `source` path** in the verifier (NOT the host `destination`); `destination` only controls where it is saved on the host (`upload_artifacts` / `_upload_target_source`, artifact_handler.py:177-249, 408-417; docs confirm). The convention dir maps to the verifier's convention dir.

**Sanitization (security-critical for TraceContract, see §7):** uploads go through `copy_via_tar` + tar extraction with Python's `data` filter (`tar_transfer.py:66-109`, `artifact_handler.py:194-249`). The `data` filter clears setuid/setgid bits, skips special files and symlinks that point outside the artifact, and normalizes permissions (docs §tasks/separate-verifier "Sanitize artifacts"). Skipped entries are logged as warnings. **Artifact contents are still untrusted input** — the verifier must still treat candidate code as hostile.

**To transfer ONLY approved artifacts:** declare exactly the agent-produced files the verifier needs in the `artifacts` list and nothing more. Undeclared files do not reach the separate verifier. **Probe confirmed:** my `solve.sh` wrote `/app/undeclared.txt`; it did not appear in the verifier (`undeclared_file_exists: false` in my `verifier/visibility.json`). My task declared only `{ source = "/app/textutil.py", destination = "candidate/textutil.py" }`; the verifier saw `/app/textutil.py` and nothing else under `/app`. (Note the automatic `/logs/artifacts/` collection is slated for removal — docs §tasks/artifacts WARNING — so for forward-compatibility, declare artifacts explicitly.)

**Manifest** (`<trial>/artifacts/manifest.json`, `ArtifactManifest`, `INST/models/trial/artifact_manifest.py`): list of `{source, destination, type: "file"|"directory", status: "ok"|"failed"|"empty"|"skipped", service, exclude}`. Collection failures are recorded without failing the trial; overlapping host paths keep the first and mark the rest `skipped` (artifact_handler.py:287-309). My reference run manifest had two `ok` entries (`/logs/artifacts`, `/app/textutil.py`).

### 5.3 Oracle and nop agents; where solution files live and how they stay hidden

- **OracleAgent** (`INST/agents/oracle.py`): `run()` copies the task's `solution/` dir to `/solution` inside the container, then executes `solve.{sh,bat}` from the working dir, stdout+stderr to `/logs/agent/oracle.txt`, with `[solution].env` layered on top (oracle.py:82-156). On nonzero exit it writes `/logs/agent/exit-code.txt` (oracle.py:154-156). `capabilities = AgentCapabilities(windows=True)` (oracle.py:22).
- **NopAgent** (`INST/agents/nop.py`): `setup`/`run` are no-ops — leaves the env exactly as built (the pre-agent baseline). Use it to score "the repository as shipped".
- **How the solution is hidden from a real evaluated agent:** `solution/` is a host-side task input. It is copied into the container ONLY by the Oracle's `run()`. For any non-oracle/non-nop agent, Harbor never uploads `/solution` — the agent env is built from `environment/` only. My probe confirmed the separate verifier also does not see `/solution` (`solution_exists: false` in `visibility.json`), because the verifier starts a fresh container from `environment/`/`tests/`. Lint rule `agent-image-test-leak` flags `COPY`/`ADD` of `tests/test.sh`, `tests/test_*.py`, or `solution/solve.sh` into the **agent** Dockerfile (`INST/lint/task.py:517-532`), i.e. the one leak path (baking hidden inputs into the agent image) is lint-guarded.
- **Trajectory seeding skips oracle/nop:** `_resolve_load_trajectory` (trial.py:1342-1365) does NOT load a task `trajectory.json` for oracle/nop ("the oracle runs the task's own solution and nop does nothing", trial.py:1351-1355). So TraceContract's prior-context trajectory is ignored when scoring candidates via oracle/nop — which is what we want (we apply candidates deterministically, not via a real agent).
- **TraceContract pattern used in §8:** store all held-out candidates under `solution/candidates/<name>.py` and have `solve.sh` select one by an env var (`CANDIDATE`), chosen per-agent via `agent.env` in the job config or `--ae CANDIDATE=<name>`. This reuses the Oracle as a deterministic "apply this candidate patch" driver and keeps every candidate hidden from the agent env and the verifier (only the applied `/app/textutil.py` is declared as an artifact). This is exactly the docs "multiple solutions" pattern (§tasks/solution).

---

## 6. ATIF trajectory format (schema, version, extension fields)

Pydantic models in `INST/models/trajectories/` (RFC 0001 = `MAIN/rfcs/0001-trajectory-format.md`, v1.8, "April 2026", maintainer "Boxuan Li").

- `Trajectory` (trajectory.py:47-142): `schema_version: Literal["ATIF-v1.0" … "ATIF-v1.8"] = "ATIF-v1.8"` (accepts v1.0–v1.8); `session_id: str|None` (run-scoped, may be shared); `trajectory_id: str|None` (document-unique; required for embedded subagents); `agent: Agent` (required); `steps: list[Step]` (min 1, **step_id sequential from 1**, validator trajectory.py:155-165); `notes: str|None`; `final_metrics: FinalMetrics|None`; `continued_trajectory_ref: str|None`; **`extra: dict[str,Any]|None`** (custom root-level metadata); `subagent_trajectories: list[Trajectory]|None`.
- `model_config = {"extra": "forbid"}` on every model — **undeclared top-level/step/tool fields are rejected.** The ONLY extension points are the typed `extra: dict[str,Any]|None` fields.
- `extra` fields exist on: `Trajectory` (root), `Agent`, `FinalMetrics`, `Step`, `ToolCall`, `Metrics`, `ObservationResult`, `SubagentTrajectoryRef` (confirmed in each model file; RFC v1.7 changelog added `extra` to ToolCall/ObservationResult, and root-level `extra`).
- `Step` (step.py:14-139): `step_id>=1`, `timestamp` (ISO-8601 validated), `source: "system"|"user"|"agent"`, `model_name`, `reasoning_effort`, `message: str | list[ContentPart]`, `reasoning_content`, `tool_calls: list[ToolCall]|None`, `observation: Observation|None`, `metrics: Metrics|None`, `is_copied_context: bool|None`, `llm_call_count: int|None`, `extra`. Agent-only fields (model_name, reasoning_effort, reasoning_content, tool_calls, metrics) are rejected on non-agent steps (step.py:104-121).
- `ToolCall` (tool_call.py): `tool_call_id`, `function_name`, `arguments: dict`, `extra`. `Observation.results[*].source_call_id` must reference a tool_call_id in the same step (trajectory.py:199-220).

**Validation:** `python -m harbor.utils.trajectory_validator <file>` (`--no-validate-images` to skip media checks). Exit 0 valid, exit 1 invalid (probed). Also `TrajectoryValidator` class.

**PROBE — can we attach TraceContract provenance / requirement links?** Yes, but ONLY inside `extra` dicts.
- `extra={"tracecontract": {...}}` at root, step, tool-call, observation-result level all validate. My `trajectory_with_provenance.json` (root `extra`, step `extra` with `requirement_ids`/`role`, tool-call `extra` with `code_state`, observation `extra` with `diff_sha256`) -> validator "✓ Trajectory is valid".
- A sibling custom key OUTSIDE `extra` is rejected: adding root `provenance` -> "trajectory.provenance: unexpected field (not part of ATIF schema)"; adding step `requirement_ids` -> "trajectory.steps.2.requirement_ids: unexpected field". So **all TraceContract metadata (session provenance, requirement ids, user-correction turn indices, diff hashes, requirement→reward-label links) must be nested under `extra`.**
- Harbor's task-level `trajectory.json` is validated as a full ATIF document before the agent runs (`_validate_task_trajectory_document`, trial.py:1384-1392), and loading it requires an agent with `capabilities.load_atif_trajectory`; oracle/nop ignore it (§5.3). The run-level alternative is `--load-trajectory <file.json>` (ATIF) / `.jsonl` (native). For TraceContract, the ATIF `extra` fields are a safe provenance carrier that survives Harbor's strict validation.

---

## 7. Security-relevant facts (Docker provider)

- **Does the verifier run in the same container as agent-modified files by default?** Depends on mode. 0.25.0 `harbor task init` / `harbor init --task` **default to `environment_mode = "separate"`** and generate a `tests/Dockerfile` that bundles tests (docs §tasks/verifier NOTE; CHANGELOG "Breaking (task initialization)"). In **shared** mode the verifier runs `/tests/test.sh` in the SAME container the agent used, seeing the agent's filesystem changes. In **separate** mode it runs in a fresh container built from `environment/`/`tests/`, with no agent filesystem changes except declared artifacts (which are tar-`data`-filtered, §5.2). Lint default rule `shared-verifier` flags shared mode (`INST/lint/task.py:277-281`). **For TraceContract reward-fidelity work, use separate mode** so the candidate cannot tamper with the grader's own files or the test harness.
- **Can code under test write the reward file location?** In shared mode, yes during the agent phase — but `Verifier._remove_reward_files()` deletes `/logs/verifier/reward.{txt,json}` (as root) before running the test (§4.1), so a pre-written reward cannot survive into grading. In separate mode the reward dir is a fresh, empty, verifier-owned dir (`empty_dirs([verifier_dir], chmod=True)`, trial.py:1045) and the agent's container is already gone. **A defense-in-depth harden (used in §8): run candidate code as an unprivileged user and have a trusted root checker delete any `reward.*` the candidate planted, then write the real reward.** My `tamper` candidate wrote `/logs/verifier/reward.json={"reward":1}` on import; under the hardened verifier it was still scored `0` (checker ran candidate as `grader`, then removed `reward.*` before writing the true reward). Under a naive in-process verifier (candidate imported as root, reward.txt written last) the same tamper scored `1` — a true false-acceptance that TraceContract's verifier-audit arm is meant to catch.
- **Privileged mode / docker socket / capabilities?** The base/prebuilt compose templates request **no** `privileged`, **no** `cap_add`, and **no** docker-socket mount (`INST/environments/docker/docker-compose-build.yaml`, `docker-compose-prebuilt.yaml` — just `sleep infinity`). The **only** container with elevated caps is Harbor's own egress-control sidecar (`docker-compose-egress-control.yaml`: `cap_add: [NET_ADMIN, NET_RAW]`), used solely to enforce `no-network`/`allowlist` via an nftables+gost transparent proxy; it is added only when a non-public network mode is requested AND the host kernel supports nftables fib inet rules (`_requires_egress_control` + `_egress_control_kernel_support`, docker.py:297-307, 979-1011). Lint rules `compose-privileged`, `compose-additional-capabilities`, `compose-writable-bind-mount`, `compose-external-bind-mount`, `compose-symlink-bind-mount` catch task-authored risks (`INST/lint/compose.py:271-305`).
- **Host bind mounts Harbor adds:** per-trial it bind-mounts `verifier/`, `agent/`, (`user-agent/`), and the agent artifacts publish dir with SELinux label `z` (`_agent_env_mounts`, trial.py:2063-2096; `_harbor_log_bind_mount`, trial.py:137-149). The separate verifier only gets the `verifier/` log bind (`_verifier_env_mounts`, trial.py:1136-1147) — it does NOT bind-mount the agent dir, so the agent cannot reach the verifier's grader files through a shared mount. NOTE: on local docker 0.25.0, **auto host-mounting is OFF by default** (`auto_mounting=False`; CHANGELOG "Breaking (local sandbox outputs)"); outputs are collected after execution via `docker compose cp`. Enable live mounts with `--ek auto_mounting=true`.
- **Network isolation per phase:** `[environment]` baseline, `[agent]` (during `agent.run()` only, not setup), `[verifier]` (during `verify()`), `[verifier.environment]` (separate-verifier baseline). Docker supports `no-network`, `allowlist` (host/wildcard/IPv4/IPv6/CIDR), and `dynamic_network_policy` — but **only on Linux containers with nftables kernel support** (docs §tasks/network-policies; `docker.py` capabilities 323-349). **PROBE:** on this rootless host, a `no-network` task was **rejected at validation** — `ValueError: network_mode='no-network' is not supported by EnvironmentType.DOCKER environment` — because the egress-control kernel probe (`/proc/config.gz` CONFIG_NFT_FIB_INET) did not confirm support, so `disable_internet`/`network_allowlist` capabilities were False and `validate_network_policy_support` (base.py:975-1037) rejected the trial before building. The alpine probe image pull hit Docker Hub 429 during my run, so the exact kernel-config result is **not-attempted**; the observable effect is that **network isolation is not guaranteed on an arbitrary host and Harbor fails fast rather than silently running public.** For reproducible TraceContract sandboxing, verify egress-control works on the target host or use a cloud provider that enforces it.
- **Results aggregation is a trusted host process, not in-container.** The host Harbor process reads each `verifier/reward.*`, parses/validates it, builds `TrialResult`, and the `Job` aggregates `JobStats` on the host (`INST/job.py`, `INST/models/job/result.py`). The container only writes a reward file; it never computes the aggregate. Secrets in trial outputs are scrubbed host-side (`_scrub_jobs_dir`, trial.py:1233-1311).

---

## 8. Minimal working example task (VALIDATED) + CLI commands

Toy task at `…/scratchpad/harbor_probe/tasks/slugify-contract` (separate verifier, non-root agent, pinned images). It encodes a 2-requirement "correction-aware contract": R1 (initial request) + R2 (user correction: ASCII-fold + 40-char cap). It carries 5 held-out candidate implementations under `solution/candidates/` selected by `CANDIDATE`. **Lint passes clean** (`harbor lint` rc=0, and `--extend-select ALL` rc=0). The whole toy (incl. all runs) is 2.2 MB.

`task.toml` (validated):
```toml
schema_version = "1.4"
source = "tracecontract-probe"
artifacts = [{ source = "/app/textutil.py", destination = "candidate/textutil.py" }]  # ONLY this reaches the separate verifier

[task]
name = "probe/slugify-contract"
version = "0.1.0"
description = "Toy correction-aware coding task used to probe Harbor 0.25.0 behavior."

[metadata]                                   # arbitrary keys; survives `lint --extend-select ALL`
tracecontract_session_id = "toy-session-001"
tracecontract_requirements = [
  { id = "R1", origin = "initial_request", turn = 1 },
  { id = "R2", origin = "user_correction", turn = 3 },
]

[verifier]
timeout_sec = 60.0
environment_mode = "separate"

[verifier.environment]
network_mode = "public"
cpus = 1
memory_mb = 1024

[agent]
timeout_sec = 120.0
user = "agent"                               # avoids the root-agent lint and runs candidate as non-root in agent env

[environment]
network_mode = "public"
cpus = 1
memory_mb = 1024
build_timeout_sec = 600.0
```
`instruction.md`: states R1 (lowercase, non-alnum→`-`, strip) and R2 ("(User correction, turn 3) The result must be pure ASCII … at most 40 characters … must not end with `-` after truncation").
`environment/Dockerfile`: `FROM python:3.12-slim@sha256:5e2bd…fa5b`; `RUN useradd --create-home --uid 1000 agent`; `WORKDIR /app`; `COPY app/ /app/`; `RUN chown -R agent:agent /app`. `environment/app/textutil.py` = a stub that raises.
`tests/Dockerfile`: `FROM python:3.12-slim@sha256:…`; `RUN useradd --create-home --uid 2000 grader`; `COPY . /tests/`; then `chmod 700 /tests/*.py /tests/test.sh; chmod 711 /tests; chmod 644 /tests/run_candidate.py` — so the unprivileged `grader` can read only the runner, never the checker data or `test.sh`.
`tests/test.sh` (hardened path): copies `/app/textutil.py` to a temp dir owned by `grader`, then `python3 -I /tests/check_contract.py` (root) which (a) runs the candidate as `grader` via `runuser -u grader -- python3 -I /tests/run_candidate.py`, capturing only its returned outputs, (b) does requirement-level property checks (exact for R1 and the ASCII cases, any-valid-truncation for the 40-char cap, so word-boundary and char-boundary truncation both pass), (c) **deletes any `reward.*` the candidate planted, then writes the true `/logs/verifier/reward.json`** `{"reward","R1","R2"}`. A `MODE=naive` branch reproduces the scaffold's in-process-import exact-match verifier for contrast.
`solution/solve.sh`: `cp /solution/candidates/${CANDIDATE:-reference}.py /app/textutil.py` (and writes an undeclared side file to prove it is not transferred). Candidates: `reference` (R1+R2 pass), `pre_correction` (R1 only — the agent's pre-correction code state), `near_miss` (ASCII+truncate but can leave trailing `-`), `alternative` (valid word-boundary truncation), `tamper` (functionally wrong; writes a fake reward on import).

**Observed scores (separate-verifier, docker, 0.25.0):**

| candidate | hardened verifier `{reward,R1,R2}` | naive exact-match verifier `reward` | human-intended |
|---|---|---|---|
| reference | 1,1,1 | 1 | accept |
| alternative (valid, word-boundary trunc) | **1,1,1** | **0** | accept — naive **false-rejects** |
| pre_correction (R1 only) | 0,1,0 | — | reject |
| near_miss (trailing `-`) | 0,1,0 | — | reject |
| tamper (planted reward) | **0,0,0** | **1** | reject — naive **false-accepts** |

This single toy already exhibits both error types TraceContract measures: the naive verifier false-accepts a reward-file-tampering candidate and false-rejects a valid alternative, while the hardened + property-based verifier gets all five right. Job-level aggregation (`harbor run` over the 5 oracle candidates + 1 nop) produced `oracle__adhoc` mean `reward=0.400, R1=0.800, R2=0.400` and `nop__adhoc` `0.000` — matching 2/5 accepts and R1 passing for all but tamper.

### 8.1 Exact CLI commands (run with `NO_COLOR=1`, `harbor` = venv bin; all rc recorded)

Scaffold / schema:
- `harbor init <org/name> --task -o <dir>` (or `harbor task init <org/name> -p <dir>`): creates `task.toml, instruction.md, environment/Dockerfile, tests/{Dockerfile,test.sh,test_outputs.py}, solution/solve.sh, README.md, .gitignore`. Flags: `--verifier-mode shared|separate` (default separate), `--no-pytest`, `--no-solution`, `--steps N`, `--include-canary-strings`, `--metadata-template <toml>`, `--no-package`. rc=0.
- `harbor task schema` / `harbor trial schema` / `harbor job schema`: print JSON Schema.

Lint / check:
- `harbor lint <task-dir>...` (static, no sandbox; needs Docker CLI only for compose rules). `--json`, `--ignore <rule>`, `--select <rule|ALL>`, `--extend-select <rule|ALL>`. Default rules exclude `root-agent` and `unpinned-image`. Exit 1 if findings, 0 if clean (my task rc=0 both default and `--extend-select ALL`). Rules enum: `INST/lint/models.py:7-24`.
- `harbor check <path>` / `harbor task check <task>`: **LLM-rubric** quality check — runs a real agent (default `claude-code`/`claude-sonnet-4-6`), needs API keys. Not run (zero-spend). `harbor task debug` also needs a model.

Run one trial locally (oracle / nop; Docker; no API key needed):
- `harbor trial start -p <task-dir> -a oracle --trials-dir <dir> --trial-name <name>` → writes `<dir>/<name>/{result.json,config.json,lock.json,verifier/reward.json,...}`. ~30 s for my task (build + separate verifier).
- Select candidate + verifier mode: `harbor trial start -p <task> -a oracle --ae CANDIDATE=alternative --ve MODE=naive --trial-name <name>`. (`--ae KEY=VALUE` = agent env; `--ve KEY=VALUE` = verifier env.)
- `harbor trial start -p <task> -a nop --trial-name nop` → scores the env as built.
- Verifier timeout override: `--verifier-timeout 5`.
- No LLM agent was ever run (oracle/nop only); zero spend.

Run a job (many candidates at once) — config form:
- `harbor run -c <job.yaml> --print-config` to inspect; `harbor run -c <job.yaml> -q -y` to execute (`-y` auto-confirms host-env prompts; `-q` quiet). JobConfig `agents: [{name: oracle, env: {CANDIDATE: reference}}, ...]`, `tasks: [{path: <task>}]`, `jobs_dir`, `n_concurrent_trials`. Result at `<jobs_dir>/<job_name>/result.json` + per-trial subdirs. My 6-trial job ran in ~85 s.

Regrade (re-verify recorded candidates with a DIFFERENT verifier, no agent rerun) — **core TraceContract primitive**:
- `harbor trial regrade <source-trial-dir> -p <updated-task-dir> --trials-dir <dir> --trial-name <name>` (also `harbor job regrade <job-dir> -p <task>`). Requires the source used a separate verifier and kept every artifact the new verifier needs (docs §jobs/regrade; CHANGELOG "Breaking (regrade)": replay materializes symlinks only to recorded agent/artifact dirs). **PROBE:** I recorded the `alternative` candidate under the property-based verifier (reward 1,1,1) and regraded it against an exact-match verifier (`[verifier.env] MODE=naive`) → reward **0.0**, in ~15 s, no agent env started. The new `result.json` records `config.source_trial = {action:"regrade", type:"local", trial_id, path}` and `lock.json` nests the source task digest. `agent_execution`/`environment_setup` are `null` (agent never ran). **This lets TraceContract score the SAME held-out candidate under all four verifiers of the 2×2 without re-running the agent — exactly the "same candidates scored by all verifiers" design.**

Other: `harbor view <jobs-dir>` (local results web viewer, ports 8080-8089); `harbor exec` (ad-hoc map/reduce job from loose files, experimental, ubuntu:latest default); `harbor task start-env -p <task>` (interactive env for debugging; `--all` adds solution+tests); `harbor agent list [--json]`, `harbor agent schema <name>`, `harbor agent auth <agent>`.

### 8.2 Housekeeping
No leftover Harbor containers or `hb__*` images persisted after runs (Harbor `down --rmi local --volumes` on delete, docker.py:1209-1215; `docker ps -a` empty, no `hb__*` images). All downloads/probes are under the scratchpad (`…/harbor_probe`, `…/dl/harbor`), total < 3 MB. No task.toml/test.sh install scripts from downloaded repos were executed.

---

## 9. 0.25.0 (INSTALLED) vs main@3bf4cb3 — differences that matter for us

Diffed INST vs MAIN (156 files differ). The ones that affect TraceContract:

1. **Error-classification model is DIFFERENT and the public docs describe MAIN, not 0.25.0.** (a) 0.25.0 `ErrorPolicy(cause: FailureCause, retry, grade)` with a derived `reward_valid`; MAIN `ErrorPolicy(should_retry, should_grade, has_valid_reward)` + `ErrorPolicyOverride` and a `TrialConfig.override_error_policy` / `JobConfig` override (error_policy.py, result.py diffs). (b) MAIN reclassifies `VerifierTimeoutError`/`RewardFileNotFoundError`/`RewardFileEmptyError`/`VerifierOutputParseError` into `should_grade=True, has_valid_reward=False`, adds `UnsupportedModelParametersError`. (c) MAIN `TrialResult`/`TrialConfig`/`JobResult` gain `schema_version: Literal[1]` and `reward_valid`/`policy` become serialized `computed_field`s; `_recorded_exceptions`→public `recorded_exceptions`; `failure_cause` removed. **Action: if you pin 0.25.0, read error semantics from `INST/models/trial/error_policy.py`, not the docs page. If you want `override_error_policy` and serialized `reward_valid`, you need a newer release than 0.25.0.**
2. **`SingleStepTrial._run_agent` exception handling widened** (single_step.py): 0.25.0 catches only `(AgentTimeoutError, NonZeroAgentExitCodeError)`; MAIN catches `Exception` and skips the verifier when `exception_info.policy.should_grade` is False. In 0.25.0 a different agent-phase exception propagates and is recorded at the `run()` boundary (still ends in `result.json.exception_info`). For oracle/nop TraceContract runs this does not bite, but a custom agent wrapper should expect 0.25.0 to be stricter about which agent errors are caught inline.
3. **`config.json` content:** 0.25.0 writes `TrialConfig.model_dump_json(exclude_defaults=True)` (sparse); MAIN writes the full config. Parse defensively (fields may be absent in 0.25.0 config.json — use `result.json.config` which is the full object, or `lock.json`).
4. MAIN adds `harbor serve`/server, `harbor environment list`, `EnvironmentOptions` (`options_model`) and stricter env kwargs, `opencode-v2`, `boxd`/`snowflake`/`superserve` providers, `unused-harborignore` + `.harborignore` lint handling, `resolve_verifier_environment_definition(..., validate_inputs=…)`, artifact Windows `service_is_dir` hardening, and scrubbing of installed-agent model keys. None change the task.toml/verifier/artifact/ATIF contracts we depend on. The `[task] version` and `schema_version="1.4"` task format is unchanged between 0.25.0 and main.

**Bottom line for the integration spec:** pin `harbor==0.25.0` and treat §2–§8 as the contract. The task.toml schema, separate-verifier artifact transfer + `data`-filter sanitization, reward.json>reward.txt precedence, pre-verify reward-file deletion, oracle candidate-selection pattern, ATIF `extra`-only provenance, and `trial regrade` all behave as documented above on 0.25.0 and are the pieces TraceContract builds on. The one place the public docs will mislead a 0.25.0 user is error classification / reward validity (§4.3, §9.1).

---

## 10. Open questions / not-attempted

- The nftables egress-control kernel probe could not be completed (Docker Hub 429 on the alpine digest); `no-network`/`allowlist` enforcement on THIS host is unconfirmed (observed: 0.25.0 rejects the trial rather than running public — fail-safe). Re-run `docker run --rm alpine@sha256:5b10f4… sh -c 'zcat /proc/config.gz | grep CONFIG_NFT_FIB_INET'` on the target host.
- `harbor check` / `harbor analyze` (LLM-rubric task quality + trajectory analysis) were not run (require API keys / spend). They are complementary to lint but not part of the reward path.
- Multi-step (`[[steps]]`, `min_reward`, `multi_step_reward_strategy`) and sidecar/compose artifact collection were read in code/docs but not executed; the single-step separate-verifier path is what §8 validated.
- Whether the Hub/registry (`harbor publish`/`upload`/Harbor Hub) is used by TraceContract is out of scope here; everything above is local-only.
