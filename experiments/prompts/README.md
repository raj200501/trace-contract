# Prompts of the model-generated artifacts

* `workflows/`: the exact script of every workflow run (contract recovery, verifier generation and audits, held-out generation and checks, brief verification, internal review, privacy fixes). Agent prompts are built from the templates in each script.
* `agent_prompts.jsonl`: the prompt of every standalone agent (e.g. controlled-session agents, held-out generators for CS-03/CS-04, reference-check writers, mappers), with the sha256 of the original prompt and transcript.

Redacted before export: quoted messages of the repository owner, session-local paths and ids, e-mail addresses. The full transcripts are kept outside the repository (they contain harness internals); their hashes are recorded here and in `tasks/*/labels/generator_audit.json`.
