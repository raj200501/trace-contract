# Third-party licences

This repository redistributes code from four upstream projects: the source
repositories of the controlled tasks. All four are under the MIT licence, which
requires its copyright notice and permission notice to be included in all copies or
substantial portions of the software.

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
| Verifier tests copied from upstream | `tasks/CS-02/verifiers/initial_plain/tests/test_existing_suite.py` and `tasks/CS-02/verifiers/initial_audited/tests/test_existing_suite.py` are mostly upstream tinydb tests. `tasks/CS-03/verifiers/initial_{plain,audited}/tests/test_preserved_behaviour.py` embed inflection's `inflection/__init__.py` at the pinned commit (docstrings removed) and reuse upstream test lines. `tasks/CS-01/verifiers/{full_plain,full_audited,llm_freeform}/tests/test_naturalsize_strip_trailing_zero.py` copy humanize's `naturalsize` as a helper or oracle, and `tasks/CS-01/verifiers/reference_check/tests/test_reference_check.py` re-implements it as `_base_naturalsize`. `tasks/CS-03/verifiers/full_{plain,audited}/tests/test_titleize_acronyms.py` copy about 15 lines of inflection's `underscore`, `humanize` and `titleize` as `_base_*` helpers, and `tasks/CS-03/verifiers/reference_check/tests/test_{underscore_unchanged,humanize_unchanged,titleize_all_caps}.py` copy inflection's `underscore`, `humanize` and `titleize`. |
| `results/runs/*/report.html` | The candidate patches, embedded as unified diffs (upstream context and removed lines). |
| `data/controlled/transcripts/*.jsonl` | Excerpts of upstream files in the agent's tool results. |

Base snapshots of the upstream repositories are not stored (the top-level
`snapshots/` is git-ignored). `tracecontract snapshot` rebuilds them from the pinned
commits.

The tinydb copyright line includes its author's e-mail address. It is kept because
the licence requires the notice to be reproduced as published.

These licences cover only the upstream code. Study-authored files (contracts,
generated verifier tests, labels, transcripts as a whole, scripts and the package)
are not covered by them. The repository's own licence is still to be decided (see
`STATUS.md`).
