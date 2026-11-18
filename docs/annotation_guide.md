# Annotation guide (v0.2)

This guide is for human reviewers of TraceContract tasks. It covers two jobs:
reviewing **contracts** (what the user actually required) and labeling
**candidates** (whether a patch is an acceptable solution). Model or rule outputs
in the repository are proposals; your decisions are the ground truth.

Record every decision in the task files with your pseudonymous reviewer id (e.g.
`R1`), never your name.

## 0. Before you start

* Read the whole source session (`tracecontract render-session tasks/<id> --out
  /tmp/<id>.txt`). For controlled tasks, user turns are scripted by the study
  (they are marked `scripted_user`).
* Do **not** look at verifier outputs (`results/`) or test files
  (`tasks/<id>/verifiers/`) before you finish labeling a task. Labels must be
  independent of the verifiers being evaluated.
* If you are the second reviewer on an overlap task, do not read the first
  reviewer's decisions until both are recorded.

## 1. Contract review

For each requirement in `tasks/<id>/contracts/reference.json`:

1. **Is it evidenced?** Every requirement must be supported by what the user said.
   Check that each quote is in the cited user message and actually means what the
   requirement states. Assistant messages are not evidence.
2. **Kind.** `change` (new/modified behaviour), `invariant` (must keep working),
   `constraint` (dependency/interface/environment limits), `non_goal` (explicitly
   out of scope).
3. **Status.** `explicit` (stated), `inferred` (implied — needs your explicit
   acceptance), `superseded` (replaced by a later user turn), `unresolved`
   (ambiguous or contradictory with no resolution — must not be scored).
4. **Later turns win.** If a later user message changes or retracts an earlier
   request, the earlier requirement must be `superseded` with a link to the newer
   one. Check that nothing superseded is still scored.
5. **Observable.** Every scored requirement needs a behavioural way to check it.
   If it is subjective or not observable, set `scored: false` (and
   `subjective: true` if it is a matter of taste).
6. **Missing requirements.** Add any requirement the user stated that is missing.

Record a review on each requirement:

```json
{"reviewer": "R1", "reviewer_kind": "human", "decision": "accept|reject|edit|needs_discussion",
 "timestamp": "2026-11-20T10:00:00Z", "note": "..."}
```

`tracecontract validate-task tasks/<id>` shows which requirements still block the
acceptance gate.

## 2. Candidate labels

A candidate is a patch against the base snapshot. Inspect it with the patch text
in `tasks/<id>/candidates/<candidate>.json` and, if needed, run it:

```
tracecontract add-candidate ...       # (already done for existing candidates)
tracecontract sandbox-python tasks/<id> <state-dir> -c '...'   # check behaviour
```

Label each **evaluation** candidate:

* **valid** — satisfies every scored, active requirement of the reference contract,
  and does not break existing behaviour that the user did not ask to change
  (the *regression norm*: the repository's existing tests for unrelated behaviour
  still pass). Different but reasonable implementation choices are valid. Behaviour
  in areas the contract marks unscored or ambiguous does not matter.
* **invalid** — violates at least one scored requirement or the regression norm.
  List the violated requirement ids in `violated_requirements`; use
  `REGRESSION` for regression-norm violations.
* **ambiguous** — you cannot decide because the contract is genuinely ambiguous for
  this candidate. Explain in `note`. Ambiguous candidates are excluded from the
  metrics and counted.

Things that do **not** make a candidate invalid: code style, missing docs or
tests, different parameter placement that the contract allows, different error
messages unless the contract specifies them, extra (harmless) functionality.

Record the label:

```json
{"value": "valid|invalid|ambiguous", "violated_requirements": ["R-..."], "labeler": "R1",
 "labeler_kind": "human", "adjudicated": false, "timestamp": "...", "note": "..."}
```

Append it to the candidate's `labels` list (do not delete proposals; they are kept
for auditing). When two reviewers disagree, a third person or a discussion produces
an adjudicated label with `"adjudicated": true`.

## 2a. The pilot's review queue and the evidence you may use

Every held-out candidate needs a human label before the primary analysis can run.
Start with the queue in `tasks/<id>/labels/review_queue.json`. It contains no
verifier outcome; regenerate it with `python scripts/write_review_queue.py
tasks/<id>`. It lists candidates that rule D19 marked **ambiguous**, candidates
with no proposal, and candidates whose independent construction check disagrees
with the proposal. Do not use the run analysis (`results/runs/*/analysis.md`) for
this: it shows verifier outcomes.

**Form your own judgment first**, from the session, the reference contract and
the patch. Only then compare it with the recorded proposals:

* **The D19 proposal** is the last label in the candidate file, labeler
  `builder:refcheck+regression+construction:v1`. Its `note` lists:
  * the failing independent reference checks (written from the reference contract;
    they are *not* the verifiers under evaluation);
  * the failing base repository tests (regression norm);
  * the construction claim.
* **The construction check** is in `tasks/<id>/labels/construction_checks.json`. A
  second agent probed the candidate in the sandbox against the reference solution.
  It records concrete inputs with the candidate's and the reference's outputs, the
  requirements it judged violated, and whether that matches the construction claim.
  Re-run any input you rely on (`tracecontract sandbox-python ...`). Do not take the
  agent's word for it.
* **The generator's description** of what it built is in the candidate's
  `description`.

A near miss is invalid only if the behaviour it gets wrong is actually required
by an active, scored requirement. Example: a near miss that changes output for
inputs no requirement covers is **valid** under this guide, even though it was
built to be wrong. Record such cases in `note`; they are evidence about how near
misses are constructed.

Never open `tasks/<id>/verifiers/*/tests/` or `results/runs/*/results.jsonl` before
your labels for the task are recorded.

## 3. What to report

* Time spent per task (contract review and labeling separately).
* Requirements you added, removed, or re-classified, and why.
* Candidates where the proposed label was wrong.
* Any session you consider unsuitable (and why) — it goes into the rejection ledger.
