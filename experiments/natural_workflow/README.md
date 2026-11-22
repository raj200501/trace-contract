# The natural arm's per-phase workflow

`natural_phase.js` is the workflow script that D65 describes for the natural recipe of D64: one workflow per family and
phase (P1 to P7). It has not been run: the build stopped at a usage limit before the first natural agent (D66).

* Launch it with the agent tool's Workflow facility, with args `{task, phase, transcripts, config_b_model}`. `transcripts`
  is the build session's directory of workflow-agent transcripts, which the coordinators search for each run's
  transcript. `config_b_model` is the agent tool's model option for configuration B. Both are given at launch so that no
  session-local path and no model option is in the repository.
* Host coordinators run the CLI steps and log them; generators get their rendered prompt verbatim; the loops of P3
  (audit revisions) and P5 (the review loop of the reference checks, and the labeler's revision) run inside their phase.
* Agent options follow each template's source workflow (D65): the default workflow agent for the generate workflow's
  roles, the general-purpose agent type for the held-out workflow's roles (the reviewers with the source's review
  schema), configuration B for the labeler and its revision.
* After each phase, run `scripts/record_phase_end.py data/natural/tasks/<task> --phase <P>`, commit
  `data/manifests/natural_phase_ends.jsonl` alone, and push it before P6 (F7).
* The sha256 code in the script was tested against a standard implementation on 20 inputs, including the twelve proposer
  prompts.
