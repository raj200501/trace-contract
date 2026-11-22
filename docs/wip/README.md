# Unfinished natural-arm packages, kept as patches

Two code packages for the natural PR-review arm were written and reviewed, but their fix rounds did not run: the build
session's agents stopped at a usage limit on 2026-11-21 (decision log D66). Neither is needed by any reported result,
since the natural run `natural-pr-v1` has not been made. They are kept here as patches against commit `11d7996`,
outside the code tree, so that the test suite stays green and no unfinished privacy gate is relied on.

Apply one with `git apply docs/wip/<file>.patch` from the repository root, on a branch based on `11d7996` or later.
Both applied cleanly to `11d7996` when they were saved; neither contains a natural repository's name.

## `natural-analysis-wp-g.patch` (WP-G: analysis of natural runs)

* sha256 `5f8ef382ff614b476ea7a9b25c286c2721e5365c1c69737c096710d292d6b8e9`.
* Files: `src/tracecontract/analysis.py` (natural mode: case-study mode below 10 S11 tasks, the source-evidence
  block, B3 as a secondary condition, the natural first prompt, labeler handling, flags, funnel, reliability, cost and
  input hashes), `tests/test_analysis_natural.py` (new).
* State: implemented and reviewed. The review found no high-severity defect. With the patch applied, the recorded
  runs (pilot-v0.2 to fresh-v1) regenerate identically apart from code hashes, and `scripts/verify_frozen_inputs.py`
  passes.
* Open review findings (medium):
  1. The cost per accepted task leaves out the S10 time of rejected families, while the fetch bytes count every family,
     so time and bytes are on different bases.
  2. The case-study analysis lacks fields that `report.py` reads, so the HTML report crashes on a natural run of fewer
     than 10 families.
  There are also several low findings.
* 5 of its tests failed in the last full run (the reviewer had seen all 23 pass). The one inspected expects
  source-evidence rows without the field `reference_observes_correction`, which the implementation now adds. The fix
  round was to reconcile tests and implementation.

## `natural-privacy-wp-h1.patch` (WP-H1: privacy and publication tools for natural runs)

* sha256 `621d2f50fba3a1b79f5a399605ce9107241557268b9a090f40dfa732c595ed46`.
* Files: `src/tracecontract/natural_privacy.py` (new), the `--natural-texts` mode of `scripts/scan_tracked_files.py`,
  the `--natural` mode of `scripts/export_prompts.py`, `scripts/publish_natural_run.py` (new), the natural mode of
  `scripts/compare_runs.py`, and their tests (new).
* State: implemented and adversarially reviewed. Verdict: **not ready as a privacy gate**.
* Open review findings:
  1. High: a thread text shorter than the window (60 characters and 8 words) is never matched, and this includes two
     accepted families' correction comments.
  2. Medium: the export guard reads the scripts' own words "@handle" as handles and aborts every natural export.
  3. Medium: the library-frame exclusion also drops frames of the natural repository's own installed package.
  4. Further findings concern B1 check ids, the second sample's logins and texts, and a publisher whose code check can
     turn off silently.
* Its own repository test fails once the extension's tasks are present: the bare-name rule reports an ordinary word
  that is also an extension repository's name, in controlled-task files.
* The three `.gitignore` rules of this package (`tasks/NP-*/`, `results/runs/natural-*/results.jsonl` and
  `results/runs/natural-*/report.html`) only add protection, so they are committed in the code tree.

## Before the natural run

Both packages must be finished, with their review findings fixed and their tests passing, before `natural-pr-v1` is
analysed or anything from it is published (protocol §15.6, §19; decision log D64 to D66).
