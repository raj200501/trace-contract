# Cluster notes: executable SWE task/environment synthesis (TraceContract)

Cluster: executable SWE task / environment synthesis (SWE-smith, R2E-Gym, SWE-Hub, ScaleSWE, and successors).
Access date for every source below: **2026-11-13 (UTC)**. Publication / version dates are recorded separately in each entry.
No commits were made in this research step. No git commands were run inside `/home/user/trace-contract`; the only file written there is this notes file. Read-only `git log -1` was run in the reference clones listed below.

Conventions:
- "States:" or a quotation means the source says it (section given). "Code:" means I read it in the cloned source (path given). "Inference:" or "My check:" means my own reasoning or a probe I ran, not a claim by the source.
- Quotes are verbatim and at most 2 sentences.
- Downloads (papers as HTML, one shallow clone of SWE-bench, one wheel) are in `<scratchpad>/dl/env_synthesis/` (about 21 MB in total). HTML was converted to text with a stdlib-only script run with `python3 -I` from a separate scripts folder.

---

## 0. Bottom line (short)

1. **Every system in this cluster builds tasks from code history (PRs, commits, issues) or from synthetic edits (bug injection, code hollowing, TDD slicing). None uses user–agent conversations or user corrections as a task source or as a source of requirements.** The one adjacent 2026 paper that uses real user–coding-assistant sessions (The Verification Horizon, arXiv 2606.26300, Section 4) turns the user's turn-level feedback into training signals (SFT / RW-SFT / Span-KTO). It does not build executable tasks or verifiers from those sessions.
2. **The verifier is almost always the repository's tests, used in the SWE-bench way:** FAIL_TO_PASS (F2P) plus PASS_TO_PASS (P2P), checked against a gold or "oracle" patch (the inverse bug patch for synthetic bugs). Variants: generated reproduction tests (R2E-Gym, ScaleSWE, SWE-Dev/THUDM, SWE-Universe), exit-code-only scripts (SWE-Factory, SWE-Universe), and an exact-match expected status map (R2E-Gym's own environments).
3. **Validation of the verifier is almost always gold-only:** the pre-fix state must fail and the gold state must pass, sometimes with reruns for flakiness (SWE-rebench: multiple runs; SWE-rebench V2 and SWE-Bench++: 3 runs; SWE-smith: post-hoc `repair.py`). **No paper in this cluster scores a fixed, held-out set of candidate patches (near misses plus valid alternatives) against independent human acceptability labels.** The closest measurements are:
   - R2E-Gym's "toxicity" and "distinguishability" of generated tests across many agent patches, with correctness taken from SWE-bench Verified hidden tests, not from human labels (Section 4.2, App. C.3).
   - SWE-Factory's human check that its exit-code fail2pass labels match three researchers' reading of the logs (precision 100%, recall 98.3%, 1,201 instances, gold patch only).
   - Task-level LLM judges of "test correctness" or "instruction–test alignment", validated against human labels: SWE-rebench (67% accuracy), RepoForge/SPICE (68.5% on test coverage), SWE-Universe (78.72% accuracy), SWE-Bench++ (reviewer precision, recall, FPR and FNR against senior annotators), and Verification Horizon (instruct_ut_align F1 75.00–81.19).
   - Human audits of instance validity: ScaleSWE (94/100 valid), Multi-SWE-bench (68 annotators), SWE-Bench++ (82 annotators, verified subset).
4. **Reusable, permissively licensed infrastructure for small offline Python environments:**
   - SWE-bench harness (MIT): pytest log parsers, F2P/P2P grading, and a post-hoc infra-failure classifier.
   - SWE-smith (MIT): `RepoProfile`/Docker build flow, valid/eval harness with test-file revert, pytest parser, flaky-test `repair.py`, and AST procedural mutators usable to build near-miss candidates.
   - R2E-Gym (Apache-2.0): old-vs-new commit status comparison, and the toxicity/distinguishability metric definitions.
   - SWE-rebench V2 builder (MIT): LLM log-parser synthesis prompt and 3-run stability evaluation.
   - Harbor (Apache-2.0; see sibling `harbor.md`).
   - None of the upstream harnesses disables networking for test containers. **My probe:** plain `docker run --network none` on this host gives a loopback-only container where DNS and TCP fail (§6.3). That is the simplest offline-at-test-time control.

---

## 1. Sources consulted

| # | Source | URL / path | Kind | Version / pub date | Full text read? | Notes |
|---|---|---|---|---|---|---|
| S1 | SWE-smith paper (Yang et al.) | https://arxiv.org/abs/2504.21798 (HTML v2) | paper | v1 30 Apr 2025; v2 21 May 2025; NeurIPS 2025 D&B Spotlight (README) | yes (main + App. A–C, D partial) | arXiv HTML license line: CC BY-SA 4.0 |
| S2 | SWE-smith code | `/home/user/SWE-bench/SWE-smith` @ `9b74ac08118a85c39c356802f7961893af73e07f` (2026-03-21, "Add PHP language support (#233)") | code | MIT (LICENSE: "Copyright (c) 2025 John Yang") | key modules read | harness/, profiles/base.py, profiles/python.py, build_repo/, bug_gen/procedural/python/, configs/install_repo.sh, docs/guides/* |
| S3 | R2E-Gym paper (Jain et al.) | https://arxiv.org/abs/2504.07164 (HTML v1) | paper | v1 9 Apr 2025 (only version) | yes (Sec. 2–4, App. A, C) | HTML license CC BY 4.0; NeurIPS 2025 page found by search (not opened) |
| S4 | R2E-Gym code | `/home/user/R2E-Gym/R2E-Gym` @ `0d94c4eb9431cd195c55a7ea3abd54006c9a1735` (2025-07-13) | code | Apache-2.0 | key modules read | runtime/docker.py, repo_analysis/*, docs/ENV_GENERATION.md |
| S5 | SWE-Hub (Qianfan Team, Baidu; Zeng et al.) | https://arxiv.org/abs/2603.00575 | paper | v1 28 Feb 2026 | yes | HTML license CC BY 4.0; system description, no numbers (see §2.3) |
| S6 | ScaleSWE: "Immersion in the GitHub Universe: Scaling Coding Agents to Mastery" (Zhao et al.) | https://arxiv.org/abs/2602.09892 | paper | v1 10 Feb 2026 … v4 24 Mar 2026 (read v4) | yes (Sec. 2–3, App. D) | HTML license CC BY 4.0 |
| S7 | ScaleSWE repo README + LICENSE | https://raw.githubusercontent.com/AweAI-Team/ScaleSWE/main/{README.md,LICENSE} | repo files | main as fetched 2026-11-13 (commit not resolved) | yes | LICENSE text in §2.4 |
| S8 | SWE-Gym (Pan et al.) | https://arxiv.org/abs/2412.21139 | paper | v1 30 Dec 2024; v2 6 Jun 2025 | yes (Sec. 3, 5, 6) | |
| S9 | SWE-rebench (Badertdinov et al.) | https://arxiv.org/abs/2505.20411 | paper | v1 26 May 2025; v2 4 Nov 2025 (read v2) | yes (Sec. 2, 4, App. B.5, F, G, L) | HTML license CC BY 4.0 |
| S10 | SWE-rebench V2 (Badertdinov et al.) | https://arxiv.org/abs/2602.23866 | paper | v1 27 Feb 2026; v2 1 Jun 2026 (read v2); ICML 2026 (comment) | yes (Sec. 3–5) | |
| S11 | SWE-rebench V2 builder repo README + LICENSE | https://raw.githubusercontent.com/SWE-rebench/SWE-rebench-V2/main/ | repo files | MIT ("Copyright (c) 2026 SWE-rebench") | README head only | linked from the HF dataset card |
| S12 | SWE-Factory (Guo et al.) | https://arxiv.org/abs/2506.10954 | paper | v1 12 Jun 2025; v3 5 Jan 2026 (read v3) | yes (Sec. 3.3, 5.3, 6, 8, 10) | code license AGPL / commercial (§2.8) |
| S13 | SWE-Universe (Chen et al., Qwen) | https://arxiv.org/abs/2602.02361 | paper | v1 2 Feb 2026; v2 21 Sep 2026 (read v2) | yes | no release link found |
| S14 | SWE-Bench++ (Wang et al.) | https://arxiv.org/abs/2512.17419 | paper | v1 19 Dec 2025 | yes (Sec. 3–4, App. C, D) | no code link found |
| S15 | RepoForge (Chen et al.) | https://arxiv.org/abs/2508.01550 | paper | v1 3 Aug 2025; v2 3 Sep 2025 | partial (Sec. 2–3 by grep) | no code link found |
| S16 | Multi-SWE-bench (Zan et al.) | https://arxiv.org/abs/2504.02605 | paper | v1 3 Apr 2025 | partial (Sec. 3.1) | code Apache-2.0 |
| S17 | SWE-Flow (Zhang et al.) | https://arxiv.org/abs/2506.09003 | paper | v1 10 Jun 2025; v2 11 Jun 2025; "Accepted by ICML2025" | partial (by grep) | code MIT |
| S18 | SWE-Dev, feature-driven (Du et al.) | https://arxiv.org/abs/2505.16975 | paper | v1 22 May 2025; v3 6 Feb 2026 | partial (by grep) | repo DorothyDUUU/SWE-Dev: no LICENSE found at main/master |
| S19 | SWE-Dev, agent + test synthesis (Wang et al., THUDM) | https://arxiv.org/abs/2506.07636 | paper | v1 9 Jun 2025; v2 23 Jun 2025; "Accepted to Findings of ACL'25" | partial (Sec. 3.2) | code MIT |
| S20 | TRACE (Kang et al.) | https://arxiv.org/abs/2604.05336 | paper (abstract) + code | v1 7 Apr 2026; v2 2 Jul 2026 | abstract only; code read | `/home/user/ScalingIntelligence/TRACE` @ `d2db23085409555b3f13ea426f42d62cf0bbc43d` (2026-07-12), MIT |
| S21 | The Verification Horizon (Wang et al., alphabetical) | https://arxiv.org/abs/2606.26300 | paper | v1 24 Jun 2026; v2 29 Jun 2026 (read v2) | Sec. 2 and 4 read | adjacent, not env synthesis; novelty threat |
| S22 | SWE-bench harness (upstream dependency) | shallow clone of https://github.com/SWE-bench/SWE-bench @ `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` (2026-09-02), `__version__ = "5.0.2"` | code | MIT | relevant modules | plus PyPI wheel swebench 4.1.0 (uploaded 2025-09-11) inspected |
| S23 | HF Hub API / dataset cards | https://huggingface.co/api/datasets/..., datasets-server `/info` | metadata | per-dataset `lastModified` in §5 | cards: SWE-rebench-V2, SWE-prime, CalibForge (heads) | |
| S24 | Abstract-only: Skywork-SWE (2506.19290, 24 Jun 2025), SWE-bench-Live (2505.23419, v2 1 Jun 2025), BugPilot (2510.19898, v2 28 Oct 2025), SWE-Synth (2504.14757, v2 20 Dec 2025), SWE-Mirror (2509.08724, 10 Sep 2025), SWE-Lego (2601.01426, v2 7 Jan 2026) | arxiv.org/abs/<id> | abstracts | as listed | no | §2.18 |
| S25 | Sibling notes `harbor.md` | `/home/user/trace-contract/docs/research/notes/harbor.md` | internal notes | 2026-11-13 | network section only | Harbor no-network behaviour on this host |
| S26 | My Docker probe | `docker run --rm --network none --read-only python:3.12-slim` (Docker Engine 29.9.2) | experiment | 2026-11-13 | n/a | §6.3 |

Search engines were used only to find arXiv IDs. Every fact below comes from the primary source (arXiv page or HTML, code, dataset card or API), unless it is marked as coming from a search summary.

---

## 2. Per-system notes

### 2.1 SWE-smith (S1 paper, S2 code)

**Bibliographic.** "SWE-smith: Scaling Data for Software Engineering Agents". Authors: John Yang, Kilian Lieret, Carlos E. Jimenez, Alexander Wettig, Kabir Khandpur, Yanzhe Zhang, Binyuan Hui, Ofir Press, Ludwig Schmidt, Diyi Yang (Stanford, Princeton, Independent, Alibaba Qwen). arXiv 2504.21798 v1 2025-04-30, v2 2025-05-21. README states NeurIPS 2025 D&B Spotlight.

**Task source.** Synthetic bugs injected into real repositories at one pinned commit. There are four strategies (Sec. 2.1): LM Modify, LM Rewrite, Procedural AST modification, Combine bugs, and "PR Mirror" (an LM reverts a real PR's changes file by file on the *current* commit).
- "Unlike SWE-bench, we do not check out the PR's base commit, as the install specifications determined in the previous step may not be compatible with older versions of the repo." (Sec. 2.1)
- The core inversion: "define an execution environment first, and then synthesize task instances within the environment." (Sec. 2)

**Environment build and validation.**
- SWE-agent installs the latest commit (≤100 steps, Sec. 2.1; App. A.2 says claude-3-5-sonnet-20241022, $2 cost cap, 150 calls, average $0.72 and 17 steps).
- An author then manually verifies the install/test instructions and checks ">80% of existing tests pass". Manual review takes 3–20 min per repo, about 18 human hours for 128 repos, and the author "gave up on 17 repositories" (App. A.2).
- One Docker image per repo (not per task). Storage is 295 GB versus 6 TB for SWE-Gym and 4 TB for the R2E-Gym subset (Table 2). They estimate a SWE-bench-style build would need 50–150 TB.
- Code (`profiles/python.py`): a conda env `testbed` is exported by `build_repo/try_install_py.py` as `sweenv_<repo>.yml`. The image is built from SWE-bench's `get_dockerfile_env` template on base `swebench/swesmith.x86_64`, and the repo is cloned from a GitHub *mirror* org (`swesmith/<owner>__<repo>.<commit8>`) created by `RepoProfile.create_mirror()`, which `rm -rf .git`, re-inits and pushes. Image name: `swebench/swesmith.<arch>.<owner>_1776_<repo>.<commit8>`.
- Default install script `configs/install_repo.sh` tries `pip install -e .`, then `.[test]`, then `requirements-test.txt`, then profile hooks, and always installs pytest. The smoke test is `pytest -q --maxfail=1` (docs `env_construction_py.md`).
- Human labor left (Sec. 2.1): about 7 min per repo to parse install procedures and about 1 min per repo to implement a test-output parser. Creating SWE-smith "took one author ~20h of human labor".

**Validation of candidate tasks.**
- Keep patches that break ≥1 passing test. "For efficiency purposes, we also limit testing runtime to two minutes" (Sec. 2.1).
- Code: `harness/valid.py` runs the pre-gold full suite once per repo (`timeout_ref=900`s) and then each bug (`timeout=90`s). `harness/grading.py:get_valid_report` diffs the status maps into F2P/P2P/F2F/P2F lists. `harness/gather.py` keeps instances with ≥1 F2P and ≥1 P2P (docs `harnesses.md`) and pushes a branch per instance with two commits: the bug, then "Remove F2P Tests" (`gather.py:545–558`).
- The evaluation harness checks out `HEAD~1` to restore tests, applies the candidate patch, then **reverts any change to F2P/P2P test files** (`harness/utils.py`, comment "For evaluation, removes any changes to test related files").
- Flakiness: `harness/repair.py` docstring: "Given a run_evaluation log, repair task instances with flaky tests." It removes F2P/P2P tests that fail under the *gold* evaluation, and deletes the instance if F2P becomes empty. The paper does not report reruns.

**Verifier type.** SWE-bench-style F2P plus P2P. Python profile test command: `pytest --disable-warnings --color=no --tb=no --verbose`. Log parser regex `^(\S+)(\s+){status}` over verbose lines (`profiles/python.py:93–102`). Resolution uses `swebench.harness.grading.get_resolution_status` (FULL = all F2P pass and all P2P pass).

**Verifier-correctness measurement.** None. My grep of the paper for "false positive/negative", "flaky" and "reward hack" found nothing. The difficulty rater (Qwen 2.5 32B trained on 1,699 SWE-bench Verified human labels) reaches 75.3% test accuracy (Sec. 2.2). That measures difficulty, not verifier fidelity.

**Problem statements.** An LM receives the bug diff, one random F2P test's source, and the test output, and is prompted for an issue with reproduction code (Sec. 2.1). Issue generation costs 2.54¢ each. The config `configs/issue_gen/ig_v2.yaml` instructs "DO NOT GIVE AWAY THE FIX!".

**User conversations or corrections.** None. Issue text is synthetic.

**Key numbers.**
- 50,137 instances from 128 repos (Table 1). Yield: Combine 96.9% (10,092), LM Modify 56.0% (17,887), LM Rewrite 35.0% (4,173), PR Mirror 33.8% (2,344), Procedural 40.2% (15,641); overall 50.1%. Median F2P is 6 and median lines edited is 5.
- Total cost $1,360 (Sec. 2.2).
- Training: rejection-sampling fine-tuning on 5,016 trajectories (expert claude-3-7-sonnet, SWE-agent, ≤75 steps). SWE-agent-LM-32B reaches **40.2% pass@1 on SWE-bench Verified** and 30.7% on Lite. The 7B model (2k trajectories) reaches 15.2% on Verified (Table 3).
- Ablation (Qwen2.5-7B, Verified, Table 5): LM Modify 5.7, LM Rewrite 8.8, Procedural 8.6, PR Mirror 9.2 % resolved.
- Issue-text ablation: giving F2P test source "leaking the evaluation criteria causes the model to skip over writing a reproduction script" (Sec. 4.1).

**Artifacts and licenses.**
- Code: MIT.
- HF `SWE-bench/SWE-smith`: card license `mit`, lastModified 2025-12-14, ~52k instances per README.
- HF `SWE-bench/SWE-smith-py`: 50,908 rows; features `instance_id, patch, FAIL_TO_PASS, PASS_TO_PASS, image_name, repo, problem_statement`; MIT.
- Per-language sets on HF: `SWE-smith-go`, `-php`, `-java`, `-js`, `-rs`, `-ts`, `-cpp`, modified 2025-12 to 2026-03; only `-py` and `-go` carry an MIT tag.
- `SWE-bench/SWE-smith-trajectories` (MIT) and model `SWE-bench/SWE-agent-LM-32B`.
- "250+ Environments" repo `SWE-bench/SWE-smith-envs` per README (not opened).
- Docker images on Docker Hub under `swebench/swesmith.*`. No license is stated for images; inference: each contains upstream code under its own license.

**Reusable infrastructure (code facts).**
- `harness/utils.py:run_patch_in_container` creates containers with `mem_limit="10g"`, `platform="linux/x86_64"`, user root, **and no network option** (default bridge networking). Patches are applied by the cascade `git apply --verbose`, then `git apply --verbose --reject`, then `patch --batch --fuzz=5 -p1 -i` (`constants.py:GIT_APPLY_CMDS`). Inference: the fuzzy fallbacks can apply a candidate patch inexactly, which is risky when scoring near-miss candidates.
- `bug_gen/procedural/python/*`: 14 Python AST modifier classes at this commit (class: remove bases, shuffle methods, remove funcs; control flow: if/else invert, shuffle lines; operations: change, flip operator, swap operands, break chains, change constants; remove: loop, conditional, assignment, wrapper). These are directly usable to *construct near-miss candidate patches* on our small repos.
- **Dependency pin needed (my check).** SWE-smith imports `swebench.harness.docker_build` (`setup_logger`, `close_logger`) and `swebench.harness.dockerfiles` (`get_dockerfile_env`). These modules **do not exist in swebench 5.0.2** (they moved to `swebench.image_builder.*` and `swebench.logger`) but **do exist in swebench 4.1.0** (wheel inspected). So use `swebench<5` (4.1.0 is the last 4.x on PyPI, uploaded 2025-09-11). Not tested end to end.
- The mirror and GitHub-org workflow needs a GitHub token or SSH key (`profiles/base.py`). For offline local repos we would bypass `create_mirror` and `clone` and build from a local checkout. Inference.

### 2.2 R2E-Gym (S3 paper, S4 code)

**Bibliographic.** "R2E-Gym: Procedural Environments and Hybrid Verifiers for Scaling Open-Weights SWE Agents". Authors: Naman Jain, Jaskirat Singh, Manish Shetty, Liang Zheng, Koushik Sen, Ion Stoica (UC Berkeley, ANU). arXiv 2504.07164 v1 2025-04-09 (only version). **Discrepancy:** the arXiv *abstract page* text says "AgentGym", "SYNGEN" and "more than 8.7K tasks", while the v1 HTML and README say "R2E-Gym", "SweGen" and "8.1K tasks".

**Task source.** Real **commits** (not only PRs/issues) from Python repos found via SEART. Rule-based filters (App. A): ≤5 non-test files, ≤100 edited lines, patch ≤2000 chars, ≤1 deleted entity, ≤3 added entities, ≤3 edited entities, ≤10 statement-level changes. An "LLM as a judge filter" is applied on top.
- "We procedurally generate environments using only commits from GitHub repositories, reducing reliance on both human-written issues and test cases." (Sec. 2)
- Problem statements are back-translated from code plus F2P execution traces (Sec. 2, App. A).

**Environment build and validation.**
- "semi-manual": per-repo install scripts search over dependency version combinations and exit on the first success (App. A, Listing 1). "This process is semi-manual and challenging to scale".
- Code: per-repo `install_utils/<repo>_install.sh` and per-repo `base_dockerfiles/Dockerfile.<repo>` (ubuntu:22.04, uv, `git clone https://github.com/<org>/<repo>.git testbed`, `git checkout $OLD_COMMIT`, `bash install.sh`).
- `repo_testextract.py` copies the *new* commit's edited test files into `r2e_tests/`. It runs them on the new commit and then on the old commit (`run_tests.sh`, timeout 120 s), keeps commits classified `NEW_COMMIT_BETTER`, and stores `expected_test_output.json` (the new-commit status map) in the image.
- `execution_result_analysis.py:is_good_exec` requires the same test keys in old and new runs, no PASSED→non-PASSED, and ≥1 non-PASSED→PASSED. Parametrized names are collapsed to the function name for "improvement keys".
- Test generation "when the curated commits do not have associated tests" is Agentless-like, with "the ground truth patch as context" (App. A).
- `validate_docker_and_hf.py:validate_docker` asserts reward 0 before the GT patch and 1 after it. This is gold-only.

**Verifier types (code `agenthub/runtime/docker.py`).**
- (a) `_calculate_reward_r2e`: parses pytest's "short test summary info" (`execution_log_parser.parse_log_pytest`, which drops the file path and joins the remaining `::` parts with `.`, so same-named tests in different files can collide; inference) and requires **exact equality** with `expected_output_json`. That covers the same number of tests and the same status per test, including tests expected to FAIL.
- (b) `_calculate_reward_swesmith`: F2P/P2P lists, with a fallback of **substring matching** of test names ("This implementation is a hack rn").
- (c) `_calculate_reward_swebench`: uses the SWE-bench grading functions.
- Inference: (a) can falsely reject a valid patch that also fixes an expected-FAILED test, such as an XFAIL. (b) can falsely accept when an F2P name is a substring of another passing test's name. Neither was measured.
- At test time the paper adds a **hybrid verifier**: execution-based (regression plus agent-generated reproduction tests, scored by pass counts) combined with an execution-free trajectory verifier, `s^H = Top_n(s^EF) + s^EB` (Eq. 2).

**Verifier-correctness measurement (closest in cluster).** These are measured on test-time-generated tests for SWE-bench Verified candidates. "Correct" means passing SWE-bench's hidden tests, not human-labelled. Definitions are in App. C.3.
- Distinguishability(t) = 1[max over incorrect patches of Pass ≠ max over correct patches of Pass].
- Toxic(t) = 1[max over incorrect patches of Pass > max over correct patches of Pass].
- Result: "for the majority of problems, less than 20% of tests provide discriminative signal" (Sec. 4.2).
- Result: "for a small but significant subset of problems, testing agents generate toxic tests (up to 10% of total tests)" (Sec. 4.2).
- Execution-free verifier: accuracy 71.82% and Best@26 42.8%. With patch only: 68.01% and 37.6% (Fig. 7a). "verifiers disproportionately attend to agent thoughts" (Sec. 4.2).

**User conversations or corrections.** None.

**Training and results.**
- R2E-Gym has 8,135 instances. The R2E-Gym-Subset, excluding SWE-bench repos, has 4,578 instances across 10 repos (Sec. 2–3).
- SFT on 3,321 trajectories from 2,048 environments (Sonnet-3.5-v2). Pass@1 on Verified: 7B 19.0, 14B 26.8, 32B **34.4** (vs SWE-Gym-trained 10.6/16.4/20.6, Table 3).
- Real vs synthetic issues, 400 trajectories each: 28.0 vs 27.8. With thoughts 34.4 vs without 30.4. Hybrid Best@26: **51.0%**.

**Artifacts and licenses.**
- Code: Apache-2.0.
- HF `R2E-Gym/R2E-Gym-Subset` (4,578 rows; features include `docker_image, commit_hash, parsed_commit_content, execution_result_content, problem_statement, expected_output_json`) and `R2E-Gym/R2E-Gym-V1` carry an `apache-2.0` tag (both lastModified 2026-07-23).
- `R2E-Gym/R2E-Gym-Lite` and the trajectory sets have **no license tag**.
- Images are on Docker Hub under `namanjain12/<repo>_final:<commit>` (code). The README says "~300MB-500Mb" each.

**Reusable infrastructure.**
- `repo_analysis/execution_result_analysis.py` (old vs new status classification), `execution_log_parser.py`, `parse_pytest.py` (maps failing tests to error blocks), and the verifier scripts `agenthub/verifiers/run_regression_tests.py` and `run_reproduction_tests.py`.
- `DockerRuntime` passes `**docker_kwargs` to `containers.run`, so `network_mode="none"` could be injected. But `setup_env()` runs `uv pip install chardet`, which needs network, so that package must be pre-baked. Inference from code.

### 2.3 SWE-Hub (S5)

**Bibliographic.** "SWE-Hub: A Unified Production System for Scalable, Executable Software Engineering Tasks". arXiv authors: Yucheng Zeng, Shupeng Li, Daxiang Dong, Ruijie Xu, Zimo Chen, Liwei Zheng, Yuxuan Li, Zhe Zhou, Haotian Zhao, Lun Tian, Heng Xiao, Tianshu Zhu, Longkun Hao, Jianmin Wu. The HTML byline says "Qianfan Team, Baidu Inc". v1 2026-02-28.

**Task source.** Three task families on a shared substrate:
- (i) **SWE-Scale**: SWE-smith-style procedural and LLM bug injection ("Building on SWE-Smith", Sec. 1). Table 1 lists 13 procedural modifiers.
- (ii) **Bug Agent**: "system-level regressions" via contract-violating edits under sampled refactoring "motivations", plus an **Issue Agent** with a post-generation "anti-leakage filter" (Sec. 6).
- (iii) **SWE-Architect**: build-a-repo tasks by "code hollowing" of coverage-mined scopes, with DOC and API agents writing a requirement document (Sec. 7).

**Environment build and validation.**
- An Env Agent produces an idempotent `install_script`, a Test Agent produces a `test_entrypoint` plus adapters emitting `standard_result.json`, and the result is a versioned image (Sec. 4).
- Readiness is defined as invocable and parseable, explicitly not as passing: "Readiness explicitly does not imply that 'tests pass.'" (Sec. 4.2)
- Per-ecosystem readiness for Python: "a pytest-based harness is invocable and emits a structured report (e.g., JUnit XML or JSON)".
- "Verification gate": a fresh container from the candidate image runs the entrypoint, and the image is accepted only if the run "completes deterministically and emits valid machine-parseable artifacts" (Sec. 4.5).
- Execution is sandbox-per-candidate on Kubernetes with a warm container pool (Sec. 5.1).

**Verifier type.** Test partitions: T_P2F (must be non-empty) and T_P2P for repair tasks; a hidden test suite for SWE-Architect (Sec. 3.3, 5.2, 7.1).

**Verifier-correctness measurement.** None. My grep found no false positive/negative analysis.
- The authors name the "Verification Coverage Paradox": "only regressions covered by available tests can be validated and retained" (Sec. 6.4).
- They also note "trivial mutations (e.g., flipping a comparison) satisfy validity criteria yet offer limited learning signal" (Sec. 5.7).

**User conversations.** None. The "user-like issue reports" are synthetic.

**Training experiments and numbers.** None. The v1 text has no dataset counts, no percentages and no training results. My grep for `%`, counts, "release", github and huggingface found none.

**Artifacts.** None linked in v1.

**Relevance.** Design ideas only. Useful: the readiness criterion that separates env failure from test failure, the structured-report (JUnit XML) requirement, the fresh-container verification gate, and the symptom–cause separation for issue text.

### 2.4 ScaleSWE / Scale-SWE (S6, S7)

**Bibliographic.** "Immersion in the GitHub Universe: Scaling Coding Agents to Mastery". Authors: Jiale Zhao, Guoxin Chen, Fanzhe Meng, Minghao Li, Jie Chen, Hui Xu, Yongshuai Sun, Wayne Xin Zhao, Ruihua Song, Yuan Zhang, Peng Wang, Cheng Chen, Ji-Rong Wen, Kai Jia (Renmin University; BandAI, ByteDance; AweAI Team). arXiv 2602.09892 v1 2026-02-10 … v4 2026-03-24.

**Task source.** Real merged PRs. They start from about 23,000 candidate repos (top-15,000 PyPI packages plus a SEART query), filter to permissive licenses, apply an LLM-judge README filter, exclude SWE-bench Verified repos, and process "6 million pull requests" with an LLM-judge PR filter. The result is 5.2k repos and **100k instances** (Sec. 2.2–2.4).

**Environment build and validation.**
- Three SWE-agent-based agents: Environment Builder (EBA; DeepSeek v3.1/v3.2), Unit-test Creator (UCA; it writes F2P/P2P tests in an execute–analyze–refine loop), and Problem Statement Writer (PSWA; Gemini3-Pro).
- EBA trajectories are distilled into a Dockerfile by an LLM. At most 10 PRs per repo get a full EBA build; other PRs reuse the "nearest" environment by PR ID and are discarded if they fail (Sec. 2.1.2). The average is 19 instances per repo.
- Rule-based check: "(1) all P2P tests pass and F2P tests fail on the original buggy codebase; and (2) all P2P and F2P tests pass upon application of the golden patch." (Sec. 2.3)
- Test order is fixed "to prevent test pollution" (Sec. 2.3).
- "Cheating prevention" is a git-history sanitization script (App. D): hard reset, delete remotes and tags, purge `.git/logs`, `packed-refs`, and so on.

**Verifier type.** F2P/P2P. Many F2P checks are *synthetic* `f2p_script` reproduction tests from the UCA, per the README: "Because a lot of high qaulity pull request do not have author written F2P, we can only synthetic F2P." (README "Data Format"). Table 1 statistics: F2P mean 5.7 (median 2.0); P2P mean 209.0 (median 68.0).

**Verifier-correctness measurement.** The only check is the "Expert Check": "four senior Ph.D. students to manually audit 100 randomly sampled instances", with 94 valid (Sec. 2.3). There is no candidate-level false acceptance or false rejection analysis.

**User conversations.** None. The only "conversation" mention is the PR-filter prompt's "pull request conversation" (App. E).

**Training.** 71,498 trajectories (3.5B tokens) from 25k instances with DeepSeek-V3.2, then SFT of Qwen3-30B-A3B-Instruct. Verified goes from **22.0% to 64.0%** (Sec. 3.2). Under the same pipeline, Table 4 gives SWE-Gym 54.8, SWE-smith 54.6 and Scale-SWE 64.0.

**Artifacts and licenses.**
- GitHub `AweAI-Team/ScaleSWE`. LICENSE: "This work is licensed under the Creative Commons Attribution 4.0 International License. The dataset is licensed under CC0, subject to any intellectual property rights in the dataset owned by the authors." The two statements conflict; record both and treat the license as ambiguous.
- HF `AweAI-Team/Scale-SWE`: 20,181 rows; features include `image_url, patch, f2p_patch, f2p_script, FAIL_TO_PASS, PASS_TO_PASS, pre_commands`; no license tag; lastModified 2026-03-05.
- The README says a "portion" (20,000 instances) was released on 2026-02-26. Model `AweAI-Team/Scale-SWE-Agent`.

### 2.5 SWE-Gym (S8)

**Bibliographic.** "Training Software Engineering Agents and Verifiers with SWE-Gym". Authors: Jiayi Pan, Xingyao Wang, Graham Neubig, Navdeep Jaitly, Heng Ji, Alane Suhr, Yizhe Zhang. arXiv 2412.21139 v1 2024-12-30, v2 2025-06-06.

**Task source.** Real GitHub issues and PRs via SWE-bench's extraction script.
- 2,438 instances from 11 repos; 230 in SWE-Gym Lite.
- SWE-Gym Raw has 64,689 instances from 358 repos and no environments (Sec. 3). The R2E-Gym Table 1 lists "SWE-Gym Raw 66,894", which is inconsistent with the SWE-Gym paper; I use the SWE-Gym paper's number.

**Environment build and validation.**
- "we manually configure dependencies for each task instance", using SWE-Bench's execution-based validation to ensure "the gold patch … passes more unit tests than the original code".
- That took "approximately 200 human annotation hours" and 10,000 CPU core hours. Released images total 6 TB (Sec. 3.1).

**Verifier type.** SWE-bench tests for reward. A learned **outcome reward model** (Qwen2.5-Coder-32B; 2,636 balanced trajectories) is used to rerank at inference (Sec. 5.1).

**Verifier-correctness measurement.** Best@k versus Pass@k is the only verifier metric: Pass@16 is 42.8% and Best@16 is 32.0% on Verified (Sec. 5.1.1). There is no analysis of the unit tests' own false accept or false reject behavior.

**User conversations.** None.

**Training.** SFT on 491 trajectories. The 32B model reaches 20.6% on Verified and 32.0% with the verifier at k=16. Lite reaches 26.0% (abstract).

**Artifacts and licenses.** GitHub `SWE-Gym/SWE-Gym` LICENSE is **Apache-2.0**. HF `SWE-Gym/SWE-Gym` is tagged **MIT**. Lite, Raw and several trajectory sets carry no license tag.

### 2.6 SWE-rebench (S9)

**Bibliographic.** "SWE-rebench: An Automated Pipeline for Task Collection and Decontaminated Evaluation of Software Engineering Agents". Authors: Ibragim Badertdinov, Alexander Golubev, Maksim Nekrashevich, Anton Shevtsov, Simon Karasik, Andrei Andriushchenko, Maria Trofimova, Daria Litvintseva, Boris Yangel (Nebius). arXiv 2505.20411 v1 2025-05-26, v2 2025-11-04.

**Task source.** Real issue–PR pairs from GitHub Archive plus clones.
- About 450,000 PRs linked to issues created before 2025-05-01, from >30,000 permissively licensed, >75%-Python repos. After filters (PR must modify tests, 1–15 files), about 153,400 remain (Sec. 2.1).
- Final: **21,336 tasks from 3,468 repos** (Sec. 2).

**Environment build and validation.**
- Versions are grouped by `git tag` (major.minor). An "agentless" LLM pipeline (Qwen2.5-72B-Instruct) produces up to 3 JSON install recipes, refined using error logs (Sec. 2.2). This works for at least one task in 31% of repos. The install-and-validate stage yield is about 14% (App. L).
- Execution-based check: ≥1 test-patch test fails before the fix, all initially failing tests pass after it, and initially passing tests keep passing (Sec. 2.3).
- They use internal PyPI/APT mirrors and record `pip freeze` / `conda env export` "to mitigate reproducibility issues from unpinned dependencies" (Sec. 2.3).
- Flakiness: "we run tests multiple times and exclude instances that fail in at least one run." (App. B.5; the number of runs is not stated).
- App. G refinements: diff `head_commit` against `base_commit`; filter deleted test files out of directives; run with `tb=line` to detect AttributeError/ImportError signature-guessing tasks; pin dependencies.

**Verifier type.** SWE-bench F2P/P2P from the PR's test patch.

**Verifier-correctness measurement.** A task-level automated quality label. Qwen2.5-72B is fine-tuned on SWE-bench Verified annotations (more than 3,800 examples, 75/25 split, 413 validation examples) to predict Issue Clarity, Task Complexity and **Test Patch Correctness**.
- Test Patch Correctness: **67% accuracy, weighted F1 0.65** (180 high-score vs 233 low-score in validation). The high-score class has F1 0.52 (precision 0.69, recall 0.42) per Table 4.
- Complexity: 81% / 0.82. Clarity: 79% / 0.76 (Sec. 2.4, App. F).
- This is a label of task quality, not a measurement on candidate patches.
- The paper states the motivation: "flawed tests that a correct solution cannot pass, leading to incorrectly penalizing the agent." (Sec. 2.4)

**User conversations.** None.

**Training.** None in this paper; it is a dataset and a decontaminated benchmark of 294 tasks from 169 repos.

**Artifacts and licenses.** HF `nebius/SWE-rebench` is **CC-BY-4.0** (lastModified 2025-12-23). Code `SWE-rebench/SWE-bench-fork` is **MIT** (the SWE-bench license). The leaderboard is swe-rebench.com.

### 2.7 SWE-rebench V2 (S10, S11)

**Bibliographic.** "SWE-rebench V2: Language-Agnostic SWE Task Collection at Scale". Authors: Ibragim Badertdinov, Maksim Nekrashevich, Anton Shevtsov, Alexander Golubev. arXiv 2602.23866 v1 2026-02-27, v2 2026-06-01; comment "ICML 2026".

**Task source.** Real issue-linked PRs: 29.5M PRs across 145k repos, narrowed to **32,079 tasks across 20 languages and 3,617 repos** (Table 1). They also release **120,000+ PR-derived tasks** with LLM-generated statements.

**Environment build and validation.**
- Per-language base images. An interactive setup agent (mini-SWE-agent v1.14.4 with Qwen3-Coder-480B-A35B-Instruct) builds an install config once per repo at the latest mined snapshot, which is then reused for all of that repo's tasks.
- Design intent: "so tests can run without network-dependent installs at runtime." (Sec. 3.2)
- They prefer JUnit XML. A per-repo **LLM-synthesized log parser** is bootstrapped from a clean log and regenerated up to 5 times (Sec. 3.2).
- They always run the **full** suite before and after the fix. "we rerun each candidate task three times and retain only instances whose structured test outcomes remain unchanged across runs." (Sec. 3.3)
- 583,809 Docker builds (2.71 min average); final images total 26.36 TiB (Sec. 3.7).
- Only about 20% of repos succeed with a single setup attempt (Sec. 3.7).

**Verifier type.** F2P/P2P on the full suite.

**Verifier and task-quality measurement.**
- (a) Issue-clarity judges were validated against the SWE-bench Verified annotation set (1,699 instances × 3 annotators). For example, the Rebench V1 prompt scores Acc 0.67, Prec 0.76, Rec 0.22, F1 0.34. A Mixed (Avg) ensemble scores Acc 0.69, Prec 0.73, Rec 0.31, F1 0.43 (Tables 3–5). Recall is very low.
- (b) Leakage audit of 509 PR-derived tasks: 77.0% clean, 23.0% with some leakage, 2.4% with explicit solution leakage (Sec. 3.6).
- (c) **Diagnostic study.** 300 tasks × 7 models × 3 runs, with metadata labels including B1 TEST_SUITE_COUPLING, B2 IMPLICIT_NAMING and B3 EXTERNAL_DEPENDENCY. "Tests often expect specific implementation details not specified in the problem statement." (Sec. 4.3) That is a false-rejection mechanism in our terms. Code A vs B* pass@3: Gemini 34.0% vs 4.0%; GLM-4.7 34.0% vs 6.0% (Sec. 4.3, Table 7).
- None of this measures false acceptance on candidate patches against human labels.

**User conversations.** None.

**Training.** The authors state there are no end-to-end RL ablations (Sec. 5).

**Artifacts and licenses.**
- HF `nebius/SWE-rebench-V2`: 32,079 rows; features include `install_config, interface, license, meta, FAIL_TO_PASS, PASS_TO_PASS`; **CC-BY-4.0**; lastModified 2026-11-05.
- The card asks users to respect each repo's license and records "the license of each repository at the time of the commit".
- `nebius/SWE-rebench-V2-PRs` is CC-BY-4.0.
- Builder code `SWE-rebench/SWE-rebench-V2` is **MIT**. Its README lists `prompts/installer/log_parser.j2` and `scripts/eval.py --golden-eval`.

### 2.8 SWE-Factory (S12)

**Bibliographic.** "SWE-Factory: Your Automated Factory for Issue Resolution Training Data and Evaluation Benchmarks". Authors: Lianghong Guo, Yanlin Wang, Caihua Li, Wei Tao, Pengyu Yang, Jiachi Chen, Haoyu Song, Duyu Tang, Zibin Zheng. arXiv 2506.10954 v1 2025-06-12, v3 2026-01-05.

**Task source.** Real GitHub issues and PRs in four languages (Python, Java, JS, TS). The collection step fixes missing **binary test files** that SWE-bench's script drops (Sec. 3.1).

**Environment build.** **SWE-Builder**, a 4-agent loop (Repository Explorer, Environment Manager, Test Manager, Test Analyst) with an "Evaluation Environment Memory Pool" that reuses Dockerfiles and test scripts from nearby versions. Up to 5 iterations (Sec. 3.2, 4.1). With GPT-4.1-mini it builds 337 of 671 issues (50.2%) at $0.047 per instance.

**Verifier type.** An **exit-code-based** test script: the Test Manager inserts `rc=$?; echo "OMNIGRIL_EXIT_CODE=$rc"`. An instance is valid if the code is non-zero before the gold patch and zero after it (Sec. 3.3). Inference: the exit code aggregates over the selected test command, so per-test F2P/P2P separation is lost.

**Verifier-correctness measurement.** A human check of the *fail2pass labelling* on 1,201 instances, with three researchers labelling each log and resolving disagreements by discussion.
- Results: TP 923, **FP 0**, TN 262, FN 16. Precision 100%, recall 98.3%, F1 0.991 (Table 7).
- The FNs come from LLM script errors: a wrong identifier (4 of 16) or `set -e` early termination (12 of 16).
- On 2,380 individual logs, exit-code status vs manual reading has F1 1.0 (Sec. 5.3).
- Scope: gold patch only. This checks status extraction, not whether the tests encode intent.

**User conversations.** None.

**Training.** 2,809 environments and trajectories (Kimi-K2, DeepSWE scaffold). Qwen2.5-Coder-14B goes from **5.8% to 21.0%** on Verified (abstract).

**Artifacts and licenses.**
- Code `DeepSoftwareAnalytics/swe-factory`: "dual licenced", AGPL "for non-commercial purposes", with a commercial license by contacting the authors (LICENSE). **This is not permissive. Reimplement the idea rather than copy the code.**
- HF `SWE-Factory/SWE-Factory-Gym`: 430 rows; MIT tag; fields include `dockerfile, eval_script, eval_script_skeleton`.

### 2.9 SWE-Universe (S13)

**Bibliographic.** "SWE-Universe: Scale Real-World Verifiable Environments to Millions". Authors: Mouxiang Chen, Lei Zhang, Yunlong Feng, Xuwu Wang, Wenting Zhao, Ruisheng Cao, Jiaxi Yang, Jiawei Chen, Mingze Li, Zeyao Ma, Hao Ge, Zongmeng Zhang, Zeyu Cui, Dayiheng Liu, Jingren Zhou, Jianling Sun, Junyang Lin, Binyuan Hui, Zhongxin Liu. arXiv 2602.02361 v1 2026-02-02, v2 2026-09-21.

**Task source.** Issue-linked PRs from 2021–2025. About 33.3M PRs are filtered to about 1M candidates. An LLM splits each change into a test patch and a fix patch (Sec. 2.1, 4).

**Environment and verifier build.**
- A building agent (mini-swe-agent; tools `bash`, `switch-to-resolved`, `switch-to-bug`) writes `evaluation.sh`, judged only by its return code.
- "A script is considered functionally correct only if it fails (exits with a non-zero status) in the buggy state and succeeds (exits with a zero status) in the fixed state." (Sec. 2.1)
- **In-loop hacking detection**: an LLM rejects scripts that "use grep or other string-matching utilities to check the contents of source files instead of running a build or test command" (Sec. 2.1).
- Iterative validation raises held-out build success from 82.6% to 94%.
- Production builder Qwen-Next-80A3 reaches a non-hacked success rate of 75.9%. Output: **807,693 environments from 52,960 repos**, of which 717,122 are issue-linked and 90,571 are PR-only (Sec. 4, Table 2).

**Verifier-correctness measurement.**
- Benchmark of 320 PRs across 8 language groups, reporting Success with and without hack. For example, Qwen-Next-80A3 scores 78.44% without hack and 82.50% with hack (Table 1). The gap is the share of verifiers flagged as hacks.
- They acknowledge "some unit tests are misaligned with the task descriptions, which can lead to false positives or false negatives" and build a quality-judge agent with "78.72% accuracy" on a human-labeled benchmark (Sec. 2.2).
- No candidate-level false acceptance or false rejection measurement.

**User conversations.** None.

**Training.** Mid-training on 500K trajectories (30B tokens). Verified rises from 50.3% to over 61%, and Multilingual from about 31% to over 46% (Sec. 5.1). Agentic RL follows. "applied … to Qwen3-Max-Thinking and achieved a score of 75.3% on SWE-Bench Verified" (abstract).

**Artifacts.** No dataset or code release link found in the v2 HTML (my grep).

### 2.10 SWE-Bench++ (S14)

**Bibliographic.** "SWE-Bench++: A Framework for the Scalable Generation of Software Engineering Benchmarks from Open-Source Repositories". Authors: Lilin Wang, Lucas Ramalho, Alan Celestino, Phuc Anthony Pham, Yu Liu, Umang Kumar Sinha, Andres Portillo, Onassis Osunwa, Gabriel Maduekwe. arXiv 2512.17419 v1 2025-12-19.

**Task source.** Live PRs, both bug fixes and feature requests, in 11 languages. 137,048 candidate PRs give 28,513 dockerized (20.8%) and **11,133 final instances from 3,971 repos** (Sec. 4.1).

**Environment build.** Vetted Dockerfile templates (multi-stage, non-root) with LLM-filled placeholders. The agent reads the repo via MCP tools, then runs a build-feedback loop (5 retries) and a test-run feedback loop (Sec. 3.2). Python yield is 41% and C++ 9.5%.

**Validation and oracle.**
- Three states: Base, Before (base plus tests), After (full PR). Feature requests count as F2P when Before fails to build (Sec. 3.3).
- **Adaptive log parsing**: a regex is tried first, then an LLM-generated parser validated by "synthetic failure injection. An LLM modifies assertions in the code to force a failure; if the parser correctly identifies this failure, it is considered valid." (Sec. 3.3.3)
- AutoQA Layer 1: build three times. Layer 2: "We execute the 'golden solution' … three times in independent containers" and keep only identical outcomes. Layer 3: an LLM-judge for statement–oracle alignment, with "Hints" appended for implicit interface requirements. Layer 4: "False-Negative Filtering" of model-breaking instances (Sec. 3.4).

**Verifier-correctness measurement.**
- The test-validity rubric explicitly defines false negatives ("Tests too narrow") and false positives ("Missing core coverage") (App. C.2).
- Automated reviewers vs humans in detecting problematic instances (App. C.3, Table 7):
  - Claude-Sonnet-4: P 0.926, R 0.921, FPR 0.615.
  - Gemini-2.5-Pro: P 0.946, R 0.884, FPR 0.423.
  - GPT-5: P 0.952, R 0.370, FPR 0.154.
  - Senior human: P 0.964, R 0.991, FPR 0.308.
  - Lead human: P 0.963, R 0.963, FPR 0.308.
- Hint-needed classifier: 94.6% accuracy on 243 senior-labeled instances (App. D.1).
- 82 annotators built a human-verified subset (Sec. 3.4).
- These are task-level, not candidate-patch-level.

**User conversations.** None.

**Training.** Small SFT additions (145–800 trajectories) to SWE-smith's 5,016 trajectories, evaluated on SWE-bench Multilingual (300 tasks). For 7B: off-the-shelf 0/300, SWE-smith 5k 5/300, plus "Diversity" 11/300 (Sec. 4.3.3).

**Artifacts.** No code or data link found in the v1 HTML (my grep).

### 2.11 RepoForge (S15)

**Bibliographic.** "RepoForge: Training a SOTA Fast-thinking SWE Agent with an End-to-End Data Curation Pipeline Synergizing SFT and RL at Scale". Authors: Zhilong Chen, Chengzong Zhao, Boyuan Chen, Dayi Lin, Yihao Chen, Arthur Leung, Gopi Krishnan Rajbahadur, Gustavo A. Oliva, Haoxiang Zhang, Aaditya Bhatia, Chong Chun Yong, Ahmed E. Hassan. arXiv 2508.01550 v1 2025-08-03, v2 2025-09-03.

**Task source.** Real GitHub commits and issues processed by a multi-agent ReAct "RepoForge Foundry". Output: **7,304 environments on 937 images** (Sec. 3.3).

**Validation.** "RepoForge Harness … validates each image with end-to-end FAIL_TO_PASS and PASS_TO_PASS tests and automatically rolls back and learns from any failures." (Sec. 3.3) Storage is reduced 14× (1.4 GB to 0.102 GB per task) and evaluation latency by more than 70% (abstract).

**Verifier type.** F2P/P2P.

**Verifier and task-quality measurement.** **SPICE** labels clarity, test validity and difficulty: "maintaining 87.3% accuracy on issue clarity and 68.5% on test coverage" (Sec. 3.4). The cost reduction is stated as 19,600× in the body and 19,000× in the abstract, which is internally inconsistent.

**User conversations.** None.

**Training.** SFT on 1,202 instances, then RL. RepoForge-8B-Agent reaches **17.4%** on Verified (abstract).

**Artifacts.** No code or data link found in the HTML (my grep).

### 2.12 Multi-SWE-bench and Multi-SWE-RL (S16)

**Bibliographic.** "Multi-SWE-bench: A Multilingual Benchmark for Issue Resolving". Zan et al. (ByteDance), arXiv 2504.02605 v1 2025-04-03.

**Task source.** Real PRs and issues in 7 languages: Java, TS, JS, Go, Rust, C, C++. **1,632 instances from 2,456 candidates**, plus the Multi-SWE-RL release of 4,723 instances (abstract).

**Environment build.** A manual inspection of CI configs and README, then a Dockerfile with iterative fixes (Sec. 3.1.3).

**Validation.** The full test suite under three logs: run (base), test (plus test.patch) and fix (plus fix.patch). They track NONE and SKIPPED statuses, not just PASSED and FAILED (Sec. 3.1.4).

**Human validation.** 68 outsourced annotators, two per instance, with cross-review. A 14-engineer QA team enforces at least 80% accuracy (Sec. 3.1.5). Annotation results are public. Multi-SWE-RL was "constructed using the same pipeline as Multi-SWE-bench, excluding the manual verification process".

**User conversations.** None.

**Licenses.** Code is Apache-2.0. HF datasets carry `license:other`; the trajectory set is cc0-1.0.

### 2.13 SWE-Flow (S17)

**Bibliographic.** "SWE-Flow: Synthesizing Software Engineering Data in a Test-Driven Manner". Lei Zhang et al. (Qwen), arXiv 2506.09003 v1 2025-06-10, v2 2025-06-11. "Accepted by ICML2025".

**Task source.** Unit tests of real projects. A Runtime Dependency Graph is built by executing tests, then sliced into an incremental "development schedule" of partial codebase, tests and required changes. **16,061 training and 2,020 test instances** (SWE-Flow-Eval).

**Verifier type.** The project's unit tests, as pass rate. The core assumption runs directly against our concern: "Unit tests enforce strict, verifiable constraints, eliminating ambiguity inherent in natural language requirements." (Sec. 3, "Precision and Minimal Ambiguity")

**Verifier measurement.** None (a manual review of development-document quality only).

**User conversations.** None.

**Training.** SF-Coder-32B-Instruct (fine-tuned Qwen2.5-Coder-32B) improves on SWE-Flow-Eval (Fig. 4).

**License.** Code `Hambaobao/SWE-Flow` is MIT.

### 2.14 SWE-Dev, feature-driven development (S18)

**Bibliographic.** Du et al., arXiv 2505.16975 v1 2025-05-22, v3 2026-02-06.

**Task source.** 8,000 popular PyPI packages. Each test file is executed under `trace` to build call trees from tests to functions. Target functions are masked, and a PRD-like requirement is produced. **14,000 train and 500 test** instances.

**Verifier type.** Developer-authored unit tests run in Docker: "Assessment uses the original, developer-authored unit tests, validated for correct execution in a controlled environment."

**Verifier measurement.** None beyond execution checks.

**Training.** SFT, PPO and DPO results; for example, 7B easy split goes from 25.74% to 36.90% Pass@1 after SFT.

**Evaluation.** The best single-turn model reaches 22.51% on the hard split; OpenHands agents reach 56.44% (abstract).

**License.** Repo `DorothyDUUU/SWE-Dev`: no LICENSE file found at main or master.

### 2.15 SWE-Dev, agent plus test synthesis (S19)

**Bibliographic.** Haoran Wang, Zhenyu Hou, Yao Wei, Jie Tang, Yuxiao Dong (THUDM), arXiv 2506.07636 v1 2025-06-09, v2 2025-06-23. Findings of ACL'25.

**Task source.** Real issues and PRs (38,000 issues from 4,000 repos). Fail-to-pass tests are synthesized through Gherkin scenarios and then code: 2,097 F2P functions from 26k instances, 4,630 test cases in total (Sec. 3.2).

**Verifier measurement.** Indirect only. RFT on their data vs Nebius SWE-bench-extra: 15.87 vs 15.80 (900 trajectories) (Table 3).

**Training.** 7B reaches 23.4% and 32B 36.6% on Verified (abstract).

**License.** Code `THUDM/SWE-Dev` is MIT.

### 2.16 TRACE (S20; local code)

**Bibliographic.** "TRACE: Capability-Targeted Agentic Training" (Turning Recurrent Agent failures into Capability-targeted training Environments). Hangoo Kang, Tarun Suresh, Jon Saad-Falcon, Azalia Mirhoseini. arXiv 2604.05336 v1 2026-04-07, v2 2026-07-02.

**Task source.** **Agent trajectories**, both successful and failed, on the *target benchmark*. Missing capabilities are mined from them, and then a synthetic environment is built per capability (abstract).

**Code: SWE-bench variant** (`prompts/swebench/environment_generation.md`, `swebench/qwen3.6_self_trace/phase4_env_validation.py`):
- Each scenario is a 300–600 LOC stdlib-only module with 10+ pytest tests, a target test, and an oracle SEARCH/REPLACE.
- Self-test: before the fix the target test must FAIL and ≥7–8 regression tests must PASS. After the oracle the target must pass and nothing may regress.
- A "No leaked open-source library identifiers" rule applies.
- Smoke test: N=10 rollouts with an acceptance threshold "rate ≤ 0.5", plus up to 5 mutation rounds.
- The prompt asserts "No reward hacking, no LLM judge". That is a claim, not a measurement.

**Verifier measurement.** None beyond the oracle self-test and the difficulty calibration (`pipeline/calibrate_environment.py` reports pass@k and GRPO group variance).

**User corrections.** None. The source is agent failures, not user feedback.

**Results.** Abstract: +15.0 Pass@1 on SWE-Bench Verified and +15.3 on τ²-Bench. The README's "Reference results" give Qwen3.6-27B going from 68.0% to 73.2% on Verified (best-iteration checkpoint). That is a different setup from the abstract.

**License.** MIT.

### 2.17 The Verification Horizon (S21). Adjacent work and novelty threat.

**Bibliographic.** "The Verification Horizon: No Silver Bullet for Coding Agent Rewards". Binghai Wang, Chenlong Zhang, Dayiheng Liu, Jiajun Zhang, Jiawei Chen, Mingze Li, Mouxiang Chen, Rongyao Fang, Siyuan Zhang, Xuwu Wang, Yuheng Jing, Zeyao Ma, Zeyu Cui ("Authors are listed alphabetically by their first names"). arXiv 2606.26300 v1 2026-06-24, v2 2026-06-29.

**Section 2: test rewards on SWE-Universe tasks.**
- The paper defines reward faithfulness as the absence of false positives and false negatives: "faithfulness is commonly characterized by the absence of false positives (an incorrect solution passes the tests) and false negatives (a correct solution fails the tests)." (Sec. 2.1)
- It notes that SWE-Universe's buggy/fixed validation "does not by itself guarantee semantic faithfulness between the task instruction and the tests." (Sec. 2.1)
- An agentic quality judge outputs `instruct_clear` and `instruct_ut_align`, evaluated on a human-annotated benchmark (Table 1, P/R/F1). instruct_ut_align F1 ranges 75.00–81.19; the best uses examples plus the GT patch at 75.93 / 87.23 / 81.19.
- RL on quality-filtered data improves Multilingual and Pro and is comparable on Verified (Fig. 4).
- Reward hacking (agents fetching the PR or tampering with tests) is treated as an "active" form of false positive (Sec. 2.1, 2.3).

**Section 4: "User Feedback as Verifier for Real-World Agent Tasks".**
- Source: "real interaction records between a group of senior software engineers within the company and a coding assistant during their daily development work" (Sec. 4.1).
- An LLM-as-judge (Qwen-Plus) labels each round's polarity, confidence, negative reason and `user_fairness`. That yields 125,528 trajectories and 535,737 round annotations. After the first round: neutral 76.6%, negative 20.0%, positive 3.5%. Negative reasons are 56.6% execution and 21.1% misunderstanding (Sec. 4.2).
- They train SFT, RW-SFT and Span-KTO. On Verified, Span-KTO reaches 59.8% vs SFT 54.2% (Sec. 4.4.2).

**Relation to TraceContract (inference).**
- This is the closest prior work on *using user corrections as a verification signal*. But it uses them as **training rewards on the original trajectories**.
- It does **not** reconstruct executable tasks or verifiers from the sessions.
- It does **not** test whether a verifier built from the initial request alone wrongly accepts code the user later rejected.
- It does **not** score fixed candidate patches against independent human labels.
- Its `user_fairness` field (whether the user's rejection is objectively fair) is a useful precedent for our adjudication protocol.

### 2.18 Other notable systems (abstract-level only; full text not read)

- **Skywork-SWE** (arXiv 2506.19290, 2025-06-24): 10,169 Python instances from 2,531 repos, each with a runtime image. More than 8,000 runtime-validated trajectories. 38.0% pass@1 on Verified, 47.0% with test-time scaling (abstract).
- **SWE-bench-Live** (arXiv 2505.23419, v2 2025-06-01): 1,319 tasks from 93 repos (issues since 2024), each with a Docker image, built by an automated curation pipeline. The arXiv abstract renders the pipeline's name as the unexpanded macro `\method`, and I did not verify its name in the full text. Live-updatable (abstract).
- **BugPilot** (arXiv 2510.19898, v2 2025-10-28): SWE agents implement features that "unintentionally break tests". FrogBoss-32B reaches 54.6% and FrogMini-14B 45.3% pass@1 on Verified (abstract). ScaleSWE uses its bug taxonomy.
- **SWE-Synth** (arXiv 2504.14757, v2 2025-12-20): LLM agents simulate debugging to produce bug–fix pairs, tests and repair trajectories. +2.3% on Lite vs real data (abstract).
- **SWE-Mirror** (arXiv 2509.08724, 2025-09-10): "mirrors" real issues into repos that already have Gym environments. 60,671 tasks across 40 repos in 4 languages (abstract).
- **SWE-Lego** (arXiv 2601.01426, v2 2026-01-07): 32k instances (real plus synthetic) and 18k trajectories. SFT-only 52.6% (32B) on Verified, 58.8% with TTS@16 (abstract). Code repo `SWE-Lego/SWE-Lego` is Apache-2.0.
- **CalibForge** (HF card only, `AweAI-Team/CalibForge`, CC-BY-4.0, 2026-11-02): 5,026 Harbor-style terminal tasks (`instruction.md`, `task.toml`, `environment/`, `tests/`) chosen by "adversarial solver calibration". The card links paper 2608.06352, which I did not open. It is relevant only as an example of the Harbor task format at scale.
- **SWE-bench/SWE-prime** (HF, 2026-04-13): only the YAML header was read. Splits `py_double_blank_lines` (484), `py_spaces_to_tabs` (381), `py_noop` (497) with SWE-bench fields plus `modifier`. The purpose is not stated in what I read; do not cite beyond its existence.

---

## 3. Upstream SWE-bench harness facts (S22): our likely dependency

- Version: `swebench` **5.0.2** (PyPI upload 2026-08-18). Main is at `02e7a74` (2026-09-02). Releases 5.0.0/5.0.1/5.0.2 came 2026-08-17/18; 4.1.0 came 2025-09-11. License MIT.
- **Layout change (my check).** In 5.0.2, image building lives in `swebench/image_builder/{docker_build,image_spec,prepare_images}.py`, `setup_logger`/`close_logger` live in `swebench/logger.py`, and the per-language Dockerfile templates of 4.1.0 (`swebench/harness/dockerfiles/*.py`) are gone (`swebench/task/repo.py:load_dockerfiles`). As noted in §2.1, SWE-smith @9b74ac0 needs a 4.x release.
- **Networking.** In 5.0.2 `harness/run_evaluation.py`, `client.containers.create(...)` sets no `network_mode` / `network_disabled` and adds `cap_add=["SYS_ADMIN"]`, with the comment "browser sandboxes need" it. In 4.1.0 `harness/docker_build.py`, `containers.create(...)` also sets no network option (`'network' in src` is False) and takes `cap_add` from `test_spec.docker_specs.run_args`. **So upstream SWE-bench, SWE-smith and R2E-Gym all run tests with default networking.**
- `harness/infra_failure.py` (5.0.2) is a post-hoc, read-only, advisory classifier. It separates "the environment broke" from "the model's patch was wrong" using log regexes, with tiers `environment` (for example `network_unreachable: Could not resolve host|Temporary failure in name resolution`, `out_of_memory`, `container_unavailable`) and `ambiguous` (`missing_module`, `no_tests_collected`, `tests_timed_out`). Useful once networking is disabled, to label env failures separately from verifier verdicts.
- `harness/log_parsers/python.py` provides `parse_log_pytest`, `parse_log_pytest_options`, `parse_log_pytest_v2`, `parse_log_django`, `parse_log_sympy`, `parse_log_matplotlib` and `parse_log_seaborn`. `harness/grading.py` provides `get_eval_tests_report`, `get_resolution_status`, `compute_fail_to_pass` and `compute_pass_to_pass`. A comment in `_is_skip_summary` shows SWE-bench Verified's own P2P lists contain parser artifacts: "PASS_TO_PASS for pytest-dev__pytest-5262 and -7521 literally expects `[100%]`".

---

## 4. Cross-cutting comparison

| System | Task source | Env build | Env/flakiness validation | Verifier | Verifier-correctness measurement | User corrections? | Training result (headline) | License (code / data) |
|---|---|---|---|---|---|---|---|---|
| SWE-smith | synthetic bugs (LM, AST, combine, PR-mirror) on 1 commit/repo | SWE-agent install + manual review; conda env yml; 1 image/repo | >80% tests pass; 2-min limit; post-hoc flaky `repair.py` | F2P + P2P (tests hidden by "Remove F2P Tests" commit) | none | no | 40.2% Verified (32B, 5,016 trajs) | MIT / MIT |
| R2E-Gym | real commits; back-translated issues; some generated tests | semi-manual dependency search per repo; per-commit images | old-vs-new status (`NEW_COMMIT_BETTER`); gold 0→1 check | exact-match expected status map (own envs); hybrid EB+EF at test time | toxicity and distinguishability of generated tests vs hidden-test correctness | no | 34.4% pass@1; 51% Best@26 | Apache-2.0 / Apache-2.0 (Subset, V1); Lite untagged |
| SWE-Hub | synthetic bugs, agentic system-level regressions, hollowed repos | Env Agent + Test Agent → install_script, entrypoint, image | fresh-container verification gate; readiness ≠ passing | T_P2F/T_P2P; hidden tests (Architect) | none | no | none reported | no release |
| ScaleSWE | real PRs (6M → 100k) | EBA agent → Dockerfile; env reuse by nearest PR | P2P pass & F2P fail pre-fix, all pass post-fix; fixed test order | F2P (often synthetic `f2p_script`) + P2P | 100-instance expert audit: 94 valid | no | 64.0% Verified (30B-A3B) | CC BY 4.0 repo text, "dataset … CC0"; HF untagged |
| SWE-Gym | real issues/PRs (11 repos) | manual per-version deps (~200 h) | gold passes more tests | SWE-bench tests; learned ORM reranker | Best@k vs Pass@k only | no | 32.0% Best@16 | Apache-2.0 / MIT |
| SWE-rebench | real issues/PRs (21,336) | LLM "agentless" recipes; internal mirrors; pinned freeze | multiple runs, drop if any fails | F2P/P2P | LLM test-patch-correctness label: 67% acc vs SWE-bench Verified labels | no | n/a (dataset) | MIT (fork) / CC-BY-4.0 |
| SWE-rebench V2 | real issue-PRs, 20 langs (32,079) + 120k PR-derived | interactive setup agent per repo; LLM log parsers | 3 identical reruns; full suite | F2P/P2P (full suite) | clarity judges vs human (F1 ≤ 0.50); leakage audit; diagnostic labels (implicit naming etc.) | no | none (stated) | MIT / CC-BY-4.0 |
| SWE-Factory | real issues (4 langs) | 4-agent SWE-Builder + memory pool | exit code fail→pass | exit-code script | human check of fail2pass labels: P 100%, R 98.3% (gold only) | no | 14B: 5.8→21.0% | AGPL/commercial / MIT (Gym) |
| SWE-Universe | issue-linked PRs (807,693) | building agent, buggy/fixed switch tools | buggy fails, fixed passes; LLM hacking detector | `evaluation.sh` exit code | build benchmark with/without hack; quality judge 78.72% acc | no | 75.3% Verified (Qwen3-Max-Thinking) | no release found |
| SWE-Bench++ | live PRs, 11 langs (11,133) | templated Dockerfiles + LLM placeholders | 3× build, 3× gold determinism; parser checked by synthetic failure injection | F2P/P2P (incl. feature F2P) | reviewers vs humans (P/R/FPR/FNR); FP/FN rubric | no | small Multilingual gains | no release found |
| RepoForge | real commits/issues (7,304) | multi-agent Foundry; pruned images | harness F2P/P2P | F2P/P2P | SPICE 68.5% on test coverage | no | 17.4% Verified (8B) | no release found |
| Multi-SWE-bench | real PRs, 7 langs | manual Dockerfiles | 3 logs (run/test/fix), NONE/SKIPPED tracked | F2P/P2P | 68 human annotators (SWE-bench Verified rubric) | no | n/a | Apache-2.0 / "other" |
| SWE-Flow | unit tests → TDD steps | Docker per project | tests execute | unit tests | none | no | SF-Coder-32B improves | MIT |
| SWE-Dev (Du) | PyPI repos, masked functions | Docker; trace call trees | tests run | developer unit tests | none | no | SFT/RL gains | no LICENSE found |
| SWE-Dev (THUDM) | real issues + synthesized F2P tests | not detailed (grep) | F2P | synthesized tests | indirect (RFT parity) | no | 36.6% Verified (32B) | MIT |
| TRACE | agent failure trajectories → synthetic scenarios | stdlib-only modules | oracle self-test + smoke difficulty | target pytest + regression guards | none | no (agent traces) | +15.0 Verified (abstract) | MIT |
| Verification Horizon (adjacent) | SWE-Universe tasks; real user–assistant sessions | (SWE-Universe) | (SWE-Universe) | tests; rubric; user feedback; agent judge | instruct_ut_align judge vs human (F1 ≤ 81.19) | **yes, as training reward** (not task/verifier construction) | Span-KTO 59.8% Verified | paper only |

---

## 5. What prior work covers vs. TraceContract (synthesis; inference)

- **Covered thoroughly by prior work** (do not claim): converting repositories or PRs into executable Docker tasks with F2P/P2P verifiers; automated env setup by agents; flakiness reruns; LLM log-parser synthesis; LLM-generated issue text with anti-leakage filters; generated reproduction tests; hacking detection for generated verifiers; task-level LLM quality judges validated against human SWE-bench Verified annotations; learned trajectory verifiers; test toxicity and distinguishability metrics.
- **Partially covered.** False rejection of valid solutions caused by tests requiring unstated implementation details is documented as a *task pathology*: SWE-rebench V2 "Implicit Naming Requirements", SWE-Bench++ "Medium Quality … tests rely on implementation details not explicitly requested", and SWE-bench Pro's interface specs as cited in SWE-rebench V2 Related Work. Their remedies are hints or interfaces appended to the statement, not measurement against human-labelled alternatives.
- **Not covered in this cluster, as far as I can see:**
  - (a) task sources that are user–agent sessions in which the user corrected the agent;
  - (b) contracts that carry requirements introduced by later corrections;
  - (c) a fixed, held-out candidate set (naturally observed pre-correction code, constructed near-misses, valid alternatives) scored by *several* verifier types;
  - (d) false acceptance and false rejection estimated against *independent human adjudication* rather than hidden tests or LLM judges;
  - (e) a predefined verifier-audit procedure compared against ordinary generated tests in a factorial design.
- R2E-Gym (toxicity) and the Verification Horizon (FP/FN framing; user-feedback rewards) are the nearest neighbours and should be cited explicitly.

---

## 6. Reusable infrastructure for small Python repos in Docker, offline at test time

### 6.1 Components and licenses

| Component | Where | License | What to reuse | Caveats |
|---|---|---|---|---|
| SWE-bench pytest log parsers + F2P/P2P grading | `swebench/harness/log_parsers/python.py`, `harness/grading.py` (5.0.2) | MIT | parse `pytest -rA`/verbose output to a status map; FULL/PARTIAL/NO resolution | parser artifacts (e.g. `[100%]`) exist upstream |
| SWE-bench infra-failure classifier | `swebench/harness/infra_failure.py` (5.0.2) | MIT | label env failures (incl. `network_unreachable`) separately from verdicts | advisory regexes only |
| SWE-smith valid/eval harness | `swesmith/harness/{valid,grading,utils,repair,gather}.py` | MIT | pre/post status diff; hide F2P tests in the initial state; revert test-file edits before scoring; drop flaky tests after gold reruns | no network isolation; fuzzy patch fallback; needs `swebench<5`; GitHub mirror logic must be bypassed |
| SWE-smith procedural mutators | `swesmith/bug_gen/procedural/python/*.py` | MIT | generate *near-miss candidate patches* (operator flips, removed conditionals, shuffled lines…) around a reference solution | tree-sitter/libcst deps |
| SWE-smith install script | `configs/install_repo.sh`, `build_repo/try_install_py.py` | MIT | conda env + editable install + test extras; exported env yml | uses network at build time (fine) |
| R2E-Gym status comparison + metric definitions | `repo_analysis/execution_result_analysis.py`; paper App. C.3 | Apache-2.0 | old vs new classification; toxicity and distinguishability formulas | exact-match reward and substring matching are false-reject/false-accept risks (inference) |
| SWE-rebench V2 builder | `SWE-rebench/SWE-rebench-V2` (`prompts/installer/log_parser.j2`, `scripts/eval.py --golden-eval`) | MIT | LLM log-parser synthesis prompt; golden eval loop; 3-run stability | multi-language, heavier than needed |
| Harbor task format + verifier phases | `/home/user/harbor-framework/harbor` (see `harbor.md`) | Apache-2.0 | separate verifier phase, artifacts, reward files | `no-network` needs nftables egress control; rejected on this host in the sibling probe |
| TRACE self-test pattern | `TRACE/swebench/qwen3.6_self_trace/phase4_env_validation.py` | MIT | target fails pre-fix, ≥N regression guards pass, oracle passes, no regressions | synthetic scenarios only |
| ScaleSWE git sanitization | paper App. D (script) | paper CC BY 4.0 | remove future history, refs, tags and reflogs from the task repo | reimplement |
| SWE-Bench++ parser validation idea | paper Sec. 3.3.3 | n/a (idea) | synthetic failure injection to check that a parser flips PASS→FAIL | no code released |
| SWE-Factory exit-code check | paper Sec. 3.3 | idea only (code AGPL) | `rc=$?` sentinel as a fallback when per-test parsing fails | loses per-test granularity |

### 6.2 Recommended concrete stack (inference)

1. **Build phase (network allowed).** For each small Python repo, write a Dockerfile from one pinned base (for example `python:3.12-slim` by digest). Install with `pip install -e .[test]` (the SWE-smith install order). Record `pip freeze` into the image (SWE-rebench practice). Bake pytest and any plugins (`pytest-json-report`, or use `--junitxml`). Commit an image digest.
2. **Validation phase (network off).**
   - For every task, run the full suite on: (a) the initial state, (b) the reference or user-accepted final state, and (c) the pre-correction agent state. All runs use `--network none`, run 3 times, and only stable outcomes are kept (SWE-rebench V2, SWE-Bench++).
   - Store the per-test status maps.
   - Validate the parser by injecting a forced assertion failure (SWE-Bench++).
   - Use the SWE-bench infra-failure regexes to flag env failures.
3. **Scoring phase (network off).** For each candidate patch:
   - Apply it strictly with `git apply` only, and record apply failures separately (inference; avoid SWE-smith's `--reject` and `patch --fuzz=5` fallbacks).
   - Revert test files and verifier files (SWE-smith eval).
   - Run the verifier and parse with SWE-bench's parser.
   - Report per-verifier accept or reject plus infra status.
4. **Near-miss construction.** Use SWE-smith procedural mutators on the reference solution's changed functions. Keep mutants that still pass the *initial-request-only* verifier but violate a correction-introduced requirement (candidate false-acceptance probes). Human adjudication decides acceptability.

### 6.3 My probe: `--network none` works on this host

Command: `docker run --rm --network none --read-only -v <scripts>/netprobe:/probe:ro python:3.12-slim python -I /probe/probe.py` (Docker Engine 29.9.2; image `python:3.12-slim`, ID `5e2bdb1b0d54`).
Output: `{'dns': 'failed: gaierror', 'tcp_1.1.1.1:443': 'failed: OSError', 'interfaces': ['lo']}`.
So plain Docker gives a loopback-only container. This is simpler than Harbor's nftables egress-control path, which the sibling `harbor.md` reports was rejected on this rootless host.

---

## 7. Recommendation: which components to reuse

- **Reuse directly (permissive):**
  - SWE-bench 5.0.2 `log_parsers/python.py`, `grading.py` and `infra_failure.py` (MIT), vendored or imported, with our own container launcher that adds `network_mode="none"` and no `cap_add`.
  - SWE-smith's `bug_gen/procedural/python` mutators and the validation logic in `harness/grading.py:get_valid_report` (MIT). Copy the logic rather than depend on the package, because of the `swebench<5` pin and GitHub-mirror coupling.
  - R2E-Gym's toxicity and distinguishability definitions (Apache-2.0 code; paper formulas) as *secondary* metrics next to human-label FA/FR.
- **Reuse ideas, reimplement:** ScaleSWE git sanitization, SWE-Bench++ parser fault injection and 3× determinism, SWE-rebench V2 3-run stability and LLM parser prompt (MIT, could be reused), SWE-Universe hacking detection as one check inside our verifier-audit procedure, and SWE-Factory's exit-code sentinel. Do not copy SWE-Factory code, because of its AGPL / commercial license.
- **Avoid as verifier templates:** R2E-Gym exact-match `expected_output_json` (penalizes extra fixes) and substring test-ID matching. Also avoid SWE-Factory whole-command exit-code grading as the primary verifier (it cannot separate F2P from P2P). All three are inferences from code and design and should be tested in our pilot.
- **Datasets** are not needed for our core design. If used for sanity checks: SWE-smith-py (MIT) and R2E-Gym-Subset (Apache-2.0) are the cleanest licenses. SWE-rebench V2 (CC-BY-4.0) includes per-repo license metadata.

---

## 8. Design implications for TraceContract (inference)

1. Treat "gold-only" validation (pre-state fails, reference passes) as necessary but not sufficient. Our contribution is the held-out candidate set with human labels. State plainly that every pipeline in this cluster stops at gold-only plus task-level judges.
2. Validate each verifier against three code states, all with network disabled and 3 reruns: initial state, pre-correction agent state, and user-accepted final state. This is our analogue of Multi-SWE-bench's and SWE-Bench++'s three-state logs.
3. Report R2E-Gym-style toxicity and distinguishability over our candidate pool in addition to FA/FR against human labels. That makes results comparable to the nearest prior metric.
4. Make "implicit naming / interface requirements" an explicit false-rejection category. Generated tests for the correction-aware contract should only assert interfaces that the user or session actually fixed (SWE-rebench V2 B2; SWE-Bench++ hints).
5. Hide verifier tests from the agent's initial state and revert test edits before scoring (SWE-smith). Sanitize git history (ScaleSWE) so pre-correction or final states cannot leak.
6. Use strict patch application and record apply failures as their own outcome, so that fuzzy hunks never become an accept.
7. Separate infra failures from verdicts (SWE-bench infra classifier) and exclude them from FA/FR denominators, reporting them separately.
8. Pin and record environments (freeze plus image digest). Bake test plugins and any `uv`/`pip` installs into the image; R2E-Gym's runtime does a network `pip install` at setup.
9. The "competent full-session LLM reconstruction baseline" should resemble ScaleSWE's UCA/PSWA or SWE-Universe's builder (agent writes tests, self-validates on buggy/fixed states). That is the strongest prior-art baseline for verifier generation.

---

## 9. Novelty threats

- **R2E-Gym** (Sec. 4.2, App. C.3): already measures how often generated tests pass incorrect patches but fail correct ones (toxicity, up to 10% of tests) and how rarely tests distinguish candidates (<20% for most problems). Correctness comes from hidden tests, not human labels, and there are no user corrections. TraceContract must differ on labels, sources and design.
- **The Verification Horizon** (2606.26300): explicitly frames test-reward faithfulness as false positives and false negatives. It builds an instruction–test alignment judge validated on human labels, and uses **real user–coding-assistant feedback as a verifier** (125,528 trajectories). Not covered: executable task reconstruction, correction-aware contracts, FA/FR on fixed candidates.
- **SWE-Bench++** App. C: FP/FN rubric for tests, and automated reviewers vs humans with FPR and FNR. **SWE-Universe**: hacking detector plus a quality judge. **SWE-rebench V1/V2** and **RepoForge (SPICE)**: test-correctness labels vs SWE-bench Verified human annotations. Together these cover "LLM judges of verifier quality validated by humans" at task level.
- **SWE-Factory**: human-validated precision and recall of automated fail2pass validation (gold-only). This could be mistaken for "verifier accuracy measurement", so the distinction must be drawn explicitly.
- **TRACE**: trajectories → targeted executable environments. It sits close to "trace reconstruction", but uses agent failures, not user corrections.
- Outside this cluster (see sibling notes): SWE-Together, SWE-INTERACT and Trace2Eval in `swechat.md` and `trace2eval.md`.

---

## 10. Open questions

- Does SWE-Universe or the Verification Horizon release its human-annotated task-quality benchmark? The size and labeling protocol are not stated in what I read.
- What is the exact `swebench` version SWE-smith @9b74ac0 was tested with? 4.1.0 is inferred (last 4.x; imports match) but not tested.
- Do SWE-smith or R2E-Gym images run their suites fully offline? Not documented. SWE-rebench V2 states this design intent; the others do not.
- How many reruns does SWE-rebench V1 use ("multiple times")? Not stated.
- Does any 2026 env-synthesis paper not found here score fixed candidate sets against human labels? My searches found none, but the search was not exhaustive (§11).
- Are ScaleSWE's 100 audited instances and SWE-Bench++'s 82-annotator verified subset public with per-instance labels? Not checked.

---

## 11. Not accessed / limitations

- github.com web pages are blocked. I used raw.githubusercontent.com for single files and one shallow clone of SWE-bench. Commit SHAs for ScaleSWE, SWE-rebench V2, SWE-Gym and other raw-file fetches were not resolved (main as fetched on 2026-11-13). The GitHub API returned 403 for this session.
- Full text not read: Skywork-SWE, SWE-bench-Live, BugPilot, SWE-Synth, SWE-Mirror, SWE-Lego, CalibForge paper (2608.06352), SWE-bench Pro, SetUpAgent/SWEE-bench (cited by SWE-Bench++), Repo2Run, ExecutionAgent.
- Partial reads (grep-based): RepoForge, Multi-SWE-bench, SWE-Flow, both SWE-Dev papers, TRACE (abstract plus code only).
- SWE-smith-envs repo, R2E-Gym project page, NeurIPS pages and Docker Hub image metadata were not opened. Image sizes and licenses are as stated by READMEs only.
- No end-to-end run of SWE-smith or R2E-Gym harnesses was attempted (they need image pulls of hundreds of MB and GitHub mirrors). Only the `--network none` probe was run.
- Numeric tables in some HTML (for example SWE-rebench V2 Table 6, SWE-Bench++ Table 2) were not extracted. Only figures quoted above were verified.
