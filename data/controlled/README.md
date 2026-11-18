# Controlled sessions (population: `controlled`)

These are **not** natural user sessions. Each is a real run of a coding agent
(Claude Code general-purpose subagent; model recorded in each transcript) on a
pinned, permissively licensed public repository, with user turns written by this
study **before** the run (protocol CS-v1, `docs/decision_log.md` D5). The study's AI
agent, the same model as the session agent, wrote the scenarios and the reference
proposals; no human has written or reviewed them.

| Path | Content |
| --- | --- |
| `transcripts/<id>.jsonl` | Sanitised transcript: user/assistant messages, tool calls and results, timestamps, model name, token usage. Harness internals and internal ids removed; e-mail addresses redacted (D9, D21). |
| `scenarios/<id>.json` | The scenario (turn texts, intended requirements, ambiguities), hashed and logged locally before the session (not a formal preregistration; D15, D41). Added only after the task's verifiers were frozen (D12). Its SHA-256 at that time is in the decision log. |
| `reference/<id>.json` | Reference-contract proposals: the intended requirements operationalised with exact evidence quotes from the scripted turns; inferred requirements (one in CS-04) have none (D11). |

Known deviations from natural sessions:

* The correction (turn U2) is delivered through a subagent messaging channel that
  wraps it in harness framing ("The coordinator sent a message while you were
  working: …"), D10.
* The agent works under a study-imposed constraint: repository code may only be
  run through sandbox wrapper scripts.
* Scenarios were designed to contain a correction; natural correction rates and
  content are not represented.
