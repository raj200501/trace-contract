# Third-party licences

This repository redistributes code from four upstream projects: the source
repositories of the controlled tasks. All four are under the MIT licence, which
requires its copyright notice and permission notice to be included in all copies or
substantial portions of the software. It redistributes no code of the repositories of
the natural PR-review arm and no verbatim text of the dataset it screens; see the last
two sections.

Each `.txt` file in this folder is that project's licence file, copied byte for byte
from the pinned commit in `tasks/<id>/task.json` (`snapshot_source`) with
`git show <commit>:<file>`.

| Project | Upstream repository | Pinned commit | Licence (SPDX) | File here (upstream file name) | Task |
| --- | --- | --- | --- | --- | --- |
| humanize | https://github.com/python-humanize/humanize | `a95004512dde4e8f0269946bb4af754382347441` | MIT | `humanize.txt` (`LICENCE`) | CS-01 |
| tinydb | https://github.com/msiemens/tinydb | `edff96aeb2616402e9489d46e90a592c05565621` | MIT | `tinydb.txt` (`LICENSE`) | CS-02 |
| inflection | https://github.com/jpvanhal/inflection | `88eefaacf7d0caaa701af7c8ab2d0ab3f17086f1` | MIT | `inflection.txt` (`LICENSE`) | CS-03 |
| more-itertools | https://github.com/more-itertools/more-itertools | `ceafee8ce96f4bc1eb74c528bc247c91d648a0bb` | MIT | `more-itertools.txt` (`LICENSE`) | CS-04 |

## Where the upstream code is

Each path below holds code of the project of its task (`CS-01` humanize, `CS-02`
tinydb, `CS-03` inflection, `CS-04` more-itertools).

| Path | Upstream code it contains |
| --- | --- |
| `tasks/*/labels/base_tests_overlay/` | The upstream test files at the pinned commit, unchanged (byte-identical). |
| `tasks/*/verifiers/repo_tests/overlay/` | The same upstream test files. In one file per task the study added the tests of the reference solution (CS-01 `tests/test_filesize.py`, CS-02 `tests/test_storages.py`, CS-03 `test_inflection.py`, CS-04 `tests/test_more.py`); the upstream lines are unchanged. |
| `tasks/*/candidates/*.json` | Candidate patches as unified diffs against the upstream source. Their context and removed lines are upstream code. |
| `tasks/*/strata/fresh-v1/candidates/*.json` | The fresh attempts' patches, as unified diffs against the upstream source. Their context and removed lines are upstream code. |
| Verifier tests copied from upstream | `tasks/CS-02/verifiers/initial_plain/tests/test_existing_suite.py` and `tasks/CS-02/verifiers/initial_audited/tests/test_existing_suite.py` are mostly upstream tinydb tests. `tasks/CS-03/verifiers/initial_{plain,audited}/tests/test_preserved_behaviour.py` embed inflection's `inflection/__init__.py` at the pinned commit (docstrings removed) and reuse upstream test lines. `tasks/CS-01/verifiers/{full_plain,full_audited,llm_freeform}/tests/test_naturalsize_strip_trailing_zero.py` copy humanize's `naturalsize` as a helper or oracle, and `tasks/CS-01/verifiers/reference_check/tests/test_reference_check.py` re-implements it as `_base_naturalsize`. `tasks/CS-03/verifiers/full_{plain,audited}/tests/test_titleize_acronyms.py` copy about 15 lines of inflection's `underscore`, `humanize` and `titleize` as `_base_*` helpers, and `tasks/CS-03/verifiers/reference_check/tests/test_{underscore_unchanged,humanize_unchanged,titleize_all_caps}.py` copy inflection's `underscore`, `humanize` and `titleize`. `tasks/CS-04/verifiers/initial_{plain,audited}/tests/test_consecutive_groups_step.py` reuse the three `ConsecutiveGroupsTest` cases of more-itertools' `tests/test_more.py` and the three `consecutive_groups` docstring examples of `more_itertools/more.py` at the pinned commit. |
| `results/runs/*/report.html` | The candidate patches, embedded as unified diffs (upstream context and removed lines). The reports now also embed the licence notices of this folder (decision log D43); the older reports of `pilot-v0.3` and `pilot-v0.3.1` do not. |
| `data/controlled/transcripts/*.jsonl` | Excerpts of upstream files in the agent's tool results. |

Base snapshots of the upstream repositories are not stored (the top-level
`snapshots/` is git-ignored). `tracecontract snapshot` rebuilds them from the pinned
commits.

The tinydb copyright line includes its author's e-mail address, so the reports that
embed the notices, such as `results/runs/pilot-v0.3.3/report.html`, contain it too. It
is kept because the licence requires the notice to be reproduced as published.

These licences cover only the upstream code. Study-authored files (contracts,
generated verifier tests, labels, transcripts as a whole, scripts and the package)
are not covered by them. They are under the repository's own licences: the code under
the MIT licence (`LICENSE`), and the data, documentation and manuscript text under
CC BY 4.0 (`LICENSE-DATA`; decision log D84).

## Dataset of the natural PR-review arm

The natural PR-review arm screens AIDev v5. The dataset's files stay outside the
repository (`data/manifests/third_party_downloads.json`, records `aidev-v5-*`); git
holds only what was extracted from them.

| Dataset | Revision | Licence (SPDX) | Licence text | Attribution | Changes |
| --- | --- | --- | --- | --- | --- |
| AIDev v5 (`hao-li/AIDev`, https://huggingface.co/datasets/hao-li/AIDev) | tag v5 = `b37f9fd1613cfec55886105bb76721918d015dc7` | CC-BY-4.0 | https://creativecommons.org/licenses/by/4.0/ | AIDev v5: the Hugging Face dataset hao-li/AIDev at tag v5, released with Li, Zhang and Hassan, arXiv:2507.15003 and arXiv:2602.09185; licensed under CC BY 4.0 | Extracted, not copied: pull-request, review-comment, issue and repository ids; commit SHAs and pull-request head refs; repository URLs (owners that act as accounts in AIDev masked as `{owner}`) and SPDX licence values; the commented files' paths; counts, sha256 hashes of texts and the categorical verdicts of model judges. Added: 120 model-written paraphrases of qualifying review comments (31 of the first sample, 89 of the extension), each checked against the source texts. No verbatim comment, pull-request or issue text of the dataset is in git (decision log D47) |

Where the extracted material is: `data/manifests/screening_natural_aidev.json`
(funnel and sample), `screening_natural_aidev_s9.json` and
`screening_natural_aidev_s9x.json` (stage S9 and its extension, with the
paraphrases), `rejection_ledger.json`, `natural_tasks_index.json` and
`third_party_downloads.json`. The CC BY 4.0 licence covers the compilation and
disclaims warranties. The dataset card says that each source repository keeps its
original copyright and licence. The comment, pull-request and issue texts are written
by GitHub users and are not re-licensed by the repository licences; they stay out of
git (decision log D47).

## Repositories of the natural PR-review arm

The natural PR-review tasks are built from public GitHub repositories found through
AIDev v5. Each keeps its own licence: AIDev's SPDX value for each fetched repository
is in the fetch records of `data/manifests/third_party_downloads.json`, and the licence
identified from the LICENSE file at each family's base, with that file's sha256, is in
`data/manifests/natural_tasks_index.json`.

**No upstream code of a natural repository is in git.** The base snapshots, the B1
and base-test overlays, the candidate patches, generated tests that copy upstream code,
and the run logs, tracebacks, check messages and HTML reports of natural runs stay
under `data/natural/`, which git ignores (protocol §17.4); the clones stay under
`/home/user/ext/`, outside the repository. What git holds about these repositories is
their ids and URLs (in the fetch records), commit SHAs, licence identifiers, the
commented files' paths, counts, outcomes and sha256 hashes. This folder therefore
holds no licence file for these repositories. Before any file with code of a natural
repository is committed, that repository's licence notice must be added here, as for
the four controlled projects.
