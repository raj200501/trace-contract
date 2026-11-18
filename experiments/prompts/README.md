# Prompts of the model-generated artifacts

* `workflows/`: the exact script of every workflow run (contract recovery, verifier generation and audits, held-out generation and checks, brief verification, internal review). Agent prompts are built from the templates in each script. Not exported: `tracecontract-privacy-fixes` (its prompts concern the repository owner's personal context). Its changes are in the git history and summarised in `docs/internal_review.md`.
* `agent_prompts.jsonl`: the prompt of every standalone agent (e.g. controlled-session agents, held-out generators for CS-03/CS-04, reference-check writers, mappers), with the sha256 of the original prompt and transcript.

Redacted before export: quoted messages of the repository owner, the owner's personal context, session-local paths and ids, e-mail addresses. The full transcripts are kept outside the repository (they contain harness internals); their hashes are recorded here and in `tasks/*/labels/generator_audit.json`.
