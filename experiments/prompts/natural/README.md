# Prompt templates of the natural arm (`natural-pr-v1`)

These are the templates of every agent of the natural PR-review arm (protocol §15.5, §15.6, §19; decision log D64).
Each `.txt` file is one template. It keeps the text of a frozen template of the controlled study word for word, except
for the deviations its header lists and its text marks. The sources are the generate workflow `wf_b796bb4f-1dd` and
the held-out workflow `wf_b428f318-391` (both in `../workflows/`), and the labeler workflow `wf_5db2f657-fdf` of D55,
which is not exported and lies outside the repository: a byte copy is kept with the private run records, and the two
labeler templates name it by file name and sha256.

| Template | File | Source | Agents | Configuration |
| --- | --- | --- | --- | --- |
| contract:v1-natural | contract_v1-natural.txt | CONTRACT_PROMPT (generate) | contract:initial_only, contract:full_session | A |
| testgen:v1-natural | testgen_v1-natural.txt | TESTGEN (generate) | C1, C3, B2 generators | A |
| b3:v1 | b3_v1.txt | TESTGEN (generate), new | B3 generator | A |
| attack:v1-natural | attack_v1-natural.txt | ATTACK (generate) | development attacks | A |
| alt:v1-natural | alt_v1-natural.txt | ALT (generate) | development alternatives | A |
| revise:v1-natural | revise_v1-natural.txt | REVISE (generate) | C2 and C4 revisers | A |
| refcontract:v1 | refcontract_v1.txt | CONTRACT_PROMPT (generate), new | reference-contract drafter | A |
| refcheck:v1-natural | refcheck_v1-natural.txt | genPrompt refcheck (held-out) | reference-check writer | A |
| review:v1-natural | review_v1-natural.txt | reviewPrompt (held-out) | reference-check reviewers | A |
| fix:v1-natural | fix_v1-natural.txt | fixPrompt (held-out) | reference-check fixers | A |
| labeler:v1-natural | labeler_v1-natural.txt | WRITE (labelers) | independent labeler | B |
| labeler-revise:v1-natural | labeler-revise_v1-natural.txt | REVISE (labelers) | its single revision | B |
| altimpl:v1-natural | altimpl_v1-natural.txt | genPrompt alt (held-out) | eval-alt-1, eval-alt-2 | A |
| nearmiss:v1-natural | nearmiss_v1-natural.txt | genPrompt nm (held-out) | eval-nm-1 to eval-nm-3 | A |
| mapper:v1-natural | mapper_v1-natural.txt | genPrompt mapper (held-out) | mapper:v1, mapper:v1#2 | A |

The format (`natural-template/1`) is described in `scripts/check_natural_prompts.py`. In short:

* the header names the source template and describes each deviation, with its letter (a to k, as in decision log D64);
* `{NAME}` is a placeholder, filled in by the host for each agent (task id, workspace, target requirement ...);
* `{{x}}...{{/}}` marks a deviation of letter x; an empty marker marks removed source text. Markers are removed when the
  prompt is rendered.

Deviation (i), the owner-context line that six held-out templates leave out, holds only once the owner has accepted it,
before the first natural agent starts (decision log D64).

Checks, from the repository root (the script imports the package, so it runs with the repository's virtual
environment):

* `.venv/bin/python scripts/check_natural_prompts.py summary [--source-dir DIR] [--allow-missing-sources]` prints each
  template's sha256 and compares it with its source, word by word: every word outside the marked deviations must be the
  source's. The two labeler templates' source lies outside the repository: without `--source-dir` (the directory that
  holds the labeler workflow script) or `--allow-missing-sources`, the summary reports it missing and exits 1.
* `.venv/bin/python scripts/check_natural_prompts.py render TEMPLATE --variant V --set NAME=VALUE ... [--verify PROMPT_FILE]`
  renders one prompt, prints its sha256 and checks a sent prompt against it. The sha256 is the one that
  `scripts/agent_run_record.py` records as the run's `prompt_sha256`.

The rendered prompts name no path under `data/natural/`, no session-local path, no held-out candidate id and no model
identifier; the renderer refuses a prompt that does, and a host value that names a path under the private run records.
No thread text is in these files.
