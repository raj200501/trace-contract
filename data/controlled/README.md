# Controlled sessions (population: `controlled`)

These are **not** natural user sessions. Each is a real run of a coding agent
(Claude Code general-purpose subagent; model recorded in each transcript) on a
pinned, permissively licensed public repository, with user turns written by this
study **before** the run (protocol CS-v1, `docs/decision_log.md` D5). The study's AI
agent, the same model as the session agent, wrote the scenarios and the reference
proposals; no human has written or reviewed them.

| Path | Content |
| --- | --- |
| `transcripts/<id>.jsonl` | Sanitised transcript (`sanitize:v2`): user/assistant messages, tool calls and results, timestamps, entry ids (`uuid`, `parentUuid`), model name, stop reasons, token usage. Harness internals and internal session and agent ids removed; every entry relabelled with a study session id; e-mail addresses redacted (D9, D38; D41 corrects D21's counts). |
| `scenarios/<id>.json` | The scenario (turn texts, intended requirements, ambiguities), hashed and logged locally before the session (not a formal preregistration; D15, D41). Its SHA-256 at that time is in the decision log. Added only after the task's evaluated verifiers were frozen (D12); CS-04's B1 was re-selected afterwards (D31). |
| `reference/<id>.json` | Reference-contract proposals: the intended requirements operationalised with exact evidence quotes from the scripted turns; inferred requirements (one in CS-04) have none (D11). The reference contracts built from them (`tasks/<id>/contracts/reference.json`) carry the legacy proposer label `study-design:pre-registered`, which means hashed and logged locally (D41); new builds write `study-design:hashed-scenario`. |

Known deviations from natural sessions:

* The correction (turn U2) is delivered through a subagent messaging channel that
  wraps it in harness framing ("The coordinator sent a message while you were
  working: …"), D10.
* The agent works under a study-imposed constraint: repository code may only be
  run through sandbox wrapper scripts.
* Scenarios were designed to contain a correction; natural correction rates and
  content are not represented.
