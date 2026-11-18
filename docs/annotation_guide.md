# Annotation guide (v0.3)

This guide is for human reviewers of TraceContract tasks. It covers two jobs:
reviewing **contracts** (what the user actually required) and labeling
**candidates** (whether a patch is an acceptable solution). Model or rule outputs
in the repository are proposals; your decisions are the ground truth.

Record contract decisions in the task files (section 1) and candidate labels in your
packet label file (section 2), with your pseudonymous reviewer id (e.g. `R1`), never
your name.

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

## 2. Candidate labels (blinded)

Candidates are labeled from a **blinded review packet**, never from the task files.
The candidate files, their ids and the review queue show how each candidate was made
and what the label rule proposed; seeing them first would anchor your judgement.

**The coordinator** (not a reviewer) builds the packet and keeps its key:

```
tracecontract review-packet tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04 --out <packet> --key <key file> --seed <number>
```

The packet has, per task, the session (`session.txt`), the reference contract
(`reference_contract.md`), and each held-out candidate under a random id
(`candidates/<id>/changes.diff`, and `candidates/<id>/state/`, the base repository
with the change applied), in shuffled order. It holds no candidate id, origin,
description, proposal, check or verifier outcome. The key, which maps the random ids
to candidates, stays with the coordinator and must be written outside the packet.

**Each reviewer** works only from the packet. Until you have recorded every label,
do not open `tasks/*/candidates/`, `tasks/*/labels/` (including `review_queue.json`),
`tasks/*/verifiers/*/tests/`, `results/`, `paper/` or the HTML reports, and do not
discuss candidates with the other reviewer. To run code in a candidate's state (needs
the base snapshot, Docker and this repository):

```
tracecontract snapshot tasks/<id>                                                  # once per task; needs git and github.com
tracecontract sandbox-python tasks/<id> <packet>/<id>/candidates/<cid>/state -c '...'  # offline, unprivileged sandbox
```

Label each candidate in the packet:

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

Record your labels in a copy of the packet's `labels_template.json`, named
`labels_<your reviewer id>.json`, with your pseudonymous reviewer id in `reviewer` and,
for each candidate, `value`, `violated_requirements` and a short `note` with your
reason. Give the file to the coordinator.

**The coordinator** merges the files once every task has two complete reviews:

```
tracecontract merge-reviews <packet>/*/labels_*.json --key <key file>
```

It refuses to merge before then. It appends each review to the candidate's `labels`
list as a human label (labeler `human:<reviewer id>`; proposals are kept for
auditing) and lists the disagreements. For each disagreement, a third person or a
discussion produces an adjudicated label with `"adjudicated": true`, appended to the
candidate file:

```json
{"value": "valid|invalid|ambiguous", "violated_requirements": ["R-..."], "labeler": "human:<id>",
 "labeler_kind": "human", "adjudicated": true, "timestamp": "...", "note": "..."}
```

## 2a. After your labels are merged: the queue and the evidence

Only after the merge may you open the queue (`tasks/<id>/labels/review_queue.json`,
which contains no verifier outcome; regenerate it with `python
scripts/write_review_queue.py tasks/<id>`) and the recorded evidence, to note where
it disagrees with your label. Do not use the run analysis
(`results/runs/*/analysis.md`) for this: it shows verifier outcomes.

* **The D19 proposal** is the last rule label in the candidate file, labeler
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

Do not change a merged label. If the evidence changes your mind, tell the coordinator:
the change goes through adjudication, and the adjudicated label's note records that the
reviewer had seen the evidence. The primary analysis uses the adjudicated label where
one exists.

A near miss is invalid only if the behaviour it gets wrong is actually required
by an active, scored requirement. Example: a near miss that changes output for
inputs no requirement covers is **valid** under this guide, even though it was
built to be wrong. Record such cases in `note`; they are evidence about how near
misses are constructed.

Never open `tasks/<id>/verifiers/*/tests/` or `results/runs/*/results.jsonl` before
your labels for the task are merged.

## 3. What to report

* Time spent per task (contract review and labeling separately).
* Requirements you added, removed, or re-classified, and why.
* Candidates where the proposed label was wrong.
* Any session you consider unsuitable (and why) — it goes into the rejection ledger.
