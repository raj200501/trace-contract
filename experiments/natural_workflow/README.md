# The natural arm's per-phase workflow

`natural_phase.js` is the workflow script that D65 describes for the natural recipe of D64: one workflow per family and
phase (P1 to P7). It was first run after the usage limit of D66: phases P1 to P4 of the first sample's six accepted
families ran with it (D67, D68, D70), and the later phases run with it too.

* Launch it with the agent tool's Workflow facility, with args `{task, phase, transcripts, config_b_model}`. `transcripts`
  is the build session's directory of workflow-agent transcripts, which the coordinators search for each run's
  transcript. `config_b_model` is the agent tool's model option for configuration B. Both are given at launch so that no
  session-local path and no model option is in the repository.
* Host coordinators run the CLI steps and log them; generators get their rendered prompt verbatim; the loops of P3
  (audit revisions) and P5 (the review loop of the reference checks, and the labeler's revision) run inside their phase.
* Coordinators run at effort `high` (D68), keep their context small (the economy rule), and never use the task-list
  tools: the natural agents that run beside them can see the shared list's titles (D65).
* Agent options follow each template's source workflow (D65): the default workflow agent for the generate workflow's
  roles, the general-purpose agent type for the held-out workflow's roles (the reviewers with the source's review
  schema), configuration B for the labeler and its revision.
* After each phase, run `scripts/record_phase_end.py data/natural/tasks/<task> --phase <P>`, commit
  `data/manifests/natural_phase_ends.jsonl` alone, and push it before P6 (F7).
* The sha256 code in the script was tested against a standard implementation on 20 inputs, including the twelve proposer
  prompts.
