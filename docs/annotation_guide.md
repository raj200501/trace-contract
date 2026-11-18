# Annotation guide (v0.4)

v0.4 follows protocol v0.6 §14 (decision log D44). Changes from v0.3: the packet's
session holds the user turns only; candidates with identical diffs share one id; each
reviewer records contract reviews, labels and an origin guess per candidate in one
label file per task; the template is `label_template.json`; reviewer ids are `R` and one
to three digits; every task has two reviewers; a candidate whose reviewers give
different values has no final label until it is adjudicated; and the list of what
reviewers must not open is the one in the packet's README.

This guide is for human reviewers of TraceContract tasks. It covers two jobs:
reviewing **contracts** (what the user actually required) and labeling
**candidates** (whether a patch is an acceptable solution). Model or rule outputs
in the repository are proposals; your decisions are the ground truth.

Record contract decisions (section 1) and candidate labels (section 2) in your label
file from the blinded review packet, with your pseudonymous reviewer id (`R` and one to
three digits, e.g. `R1`), never your name.

## 0. Before you start

* Read the session's user turns in the packet's `session.txt`. For controlled tasks,
  user turns are scripted by the study. The packet leaves out the agent's messages and
  tool calls, which show its edits before the correction.
* Do **not** look at verifier outputs (`results/`) or test files
  (`tasks/<id>/verifiers/`), or anything else section 2 lists, until your labels have
  been merged. Labels must be independent of the verifiers being evaluated.
* Every task has two reviewers. Do not read the other reviewer's decisions, or discuss
  candidates or requirements with them, until your labels have been merged.

## 1. Contract review

For each requirement in the packet's `reference_contract.md` (its id, kind, status,
statement, observable behaviour, and the user's quotes with their event ids):

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
   request, the earlier requirement must be `superseded` by a requirement from the
   later turn. (The packet shows each status, not which requirement supersedes which.)
   Check that nothing superseded is still scored.
5. **Observable.** Every scored requirement needs a behavioural way to check it.
   If it is subjective or not observable, it must not be scored (`scored: false`, and
   `subjective: true` if it is a matter of taste): choose `edit` and say so in the note.
6. **Missing requirements.** Report any requirement the user stated that is missing,
   with its quote, to the coordinator (section 3). The label file has entries only for
   the listed requirements.

Record a decision on each requirement in the `contract_reviews` of your label file
(section 2): `accept`, `reject`, `edit` (say in `note` what to change) or
`needs_discussion`, with a `note` giving your reason:

```json
"contract_reviews": {"R-...": {"decision": "accept|reject|edit|needs_discussion", "note": "..."}}
```

The merge (section 2) appends each decision to the requirement's `reviews` in
`tasks/<id>/contracts/reference.json` as a human review (reviewer `human:<your id>`).
After the merge, `tracecontract validate-task tasks/<id>` shows which requirements
still block the acceptance gate. Without `--show-candidates` it prints no candidate's
origin or label; do not use that option before your labels have been merged.

## 2. Candidate labels (blinded)

Candidates are labeled from a **blinded review packet**, never from the task files.
The candidate files, their ids and the review queue show how each candidate was made
and what the label rule proposed; seeing them first would anchor your judgement.

**The coordinator** (not a reviewer) builds the packet from the tasks' base snapshots
(`tracecontract snapshot tasks/<id>`, once per task; needs git and github.com) and
keeps its key:

```
tracecontract review-packet tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04 --out <packet> --key <key file> --seed <number>
```

The packet has, per task, the session's user turns (`session.txt`), the reference
contract (`reference_contract.md`), the label template (`label_template.json`) and
each held-out candidate under a random id (`candidates/<id>/changes.diff`, and
`candidates/<id>/state/`, the base repository with the change applied), in shuffled
order. Candidates with identical diffs share one id. The packet's `README.md` sums up
the reviewers' instructions. The packet holds no candidate id, origin, description,
proposal, check or verifier outcome. The key, which maps the random ids to candidates,
stays with the coordinator and must be written outside the packet; `review-packet`
refuses to write it inside the packet or over an existing file.

The packet hides the origin field but not the origin. A candidate's origin can still be
inferred from its content: near misses resemble each other and the reference, and the
user's corrections describe what the agent did first, so the state before the
correction may be recognisable. Your labels are therefore not fully blind to origin.
Label each candidate by what it does, not by how you think it was made. Your origin
guess (below) measures how blind the review was.

**Each reviewer** works only from the packet. Until your labels have been merged, do not
open the repository's `tasks/`, `results/`, `paper/`, `data/`, `experiments/` or `docs/`
folders (except this guide; `data/controlled/transcripts/` holds the full sessions), its `README.md` or `STATUS.md`, any HTML report or the git history;
do not run `tracecontract validate-task --show-candidates` or `render-session`; and do
not discuss candidates or requirements with the other reviewer. To run code in a
candidate's state (needs Docker and this repository; the packet's state directories are
readable by the sandbox's unprivileged user):

```
tracecontract sandbox-python tasks/<id> <packet>/<id>/candidates/<cid>/state -c '...'  # offline, unprivileged sandbox
```

If the task's image does not exist yet, the first run builds it; that may need network
access to download the pinned packages and the base image.

Label each candidate in the packet:

* **valid** — satisfies every scored, active requirement of the reference contract,
  and does not break existing behaviour that the user did not ask to change
  (the *regression norm*: the repository's existing tests for unrelated behaviour
  still pass). Different but reasonable implementation choices are valid. Behaviour
  in areas the contract marks unscored or ambiguous does not matter.
* **invalid** — violates at least one scored requirement or the regression norm.
  List the violated requirement ids in `violated_requirements`: ids of active
  (explicit or inferred), scored requirements, or `REGRESSION` for regression-norm
  violations. The merge rejects other ids, and any list on a valid or ambiguous label.
* **ambiguous** — you cannot decide because the contract is genuinely ambiguous for
  this candidate. Explain in `note` (the merge rejects an ambiguous label without
  one). Ambiguous candidates are excluded from the metrics and counted.

Things that do **not** make a candidate invalid: code style, missing docs or
tests, different parameter placement that the contract allows, different error
messages unless the contract specifies them, extra (harmless) functionality.

Record your decisions in a copy of the task's `label_template.json` named
`labels_<your reviewer id>.json` (e.g. `labels_R1.json`), one file per task:

```json
{"task_id": "CS-01", "reviewer": "R1",
 "contract_reviews": {"R-...": {"decision": "accept|reject|edit|needs_discussion", "note": "..."}},
 "labels": {"C...": {"value": "valid|invalid|ambiguous", "violated_requirements": ["R-..."],
                     "origin_guess": "pre-correction|alternative|near-miss|unsure", "note": "..."}}}
```

* `reviewer`: your pseudonymous reviewer id, `R` and one to three digits, never your
  name. The merge rejects any other value; it writes the id into the task files.
* `contract_reviews`: a decision on every requirement (section 1).
* `labels`: for every candidate, `value` and `violated_requirements` as above, and
  `origin_guess`, your guess of how the candidate was made: `pre-correction` (the
  agent's state before the user's correction), `alternative` (an independent valid
  implementation), `near-miss` (a deliberately flawed variant) or `unsure`. The guess
  is used only to measure how blind the review was, never as a label.
* `note`: a short reason for each decision. The merge keeps the first 2,000
  characters.

The merge rejects a file that leaves out or adds a requirement or a candidate. Give the
files to the coordinator.

**The coordinator** puts each reviewer's file in its task's folder of the packet
(`<packet>/<task>/labels_<reviewer id>.json`) and merges the files once every task has
two complete reviews:

```
tracecontract merge-reviews <packet>/*/labels_*.json --key <key file>
```

The pattern does not match the templates. The merge refuses to run while any task has
fewer than two complete reviews (`--min-reviewers` defaults to 2, as protocol v0.6 §14
requires), and it refuses to merge the same packet twice; `--dry-run` checks the files
and prints the report without writing anything. It appends each review to the `labels`
list of every candidate behind the packet id, as a human label (labeler
`human:<reviewer id>`, with the origin guess in its note; proposals are kept for
auditing), and each contract decision to the reference contract (section 1). It lists
the candidates on which the reviewers' values or violated requirements differ, the
requirements on which their contract decisions differ, and how many of each
reviewer's origin guesses were right, wrong or unsure (counted once per candidate
behind each id). For each label disagreement, a third person or a discussion produces
an adjudicated label with `"adjudicated": true`, appended to the candidate file:

```json
{"value": "valid|invalid|ambiguous", "violated_requirements": ["R-..."], "labeler": "human:<id>",
 "labeler_kind": "human", "adjudicated": true, "timestamp": "...", "note": "..."}
```

Until then, a candidate whose reviewers gave different values has no final label
(`Candidate.final_label()` returns `None`), and the review queue lists it as needing
adjudication. The merge does not resolve contract disagreements either. The acceptance
gate reads only the latest human review of each requirement and counts `edit` as
acceptance, so check every contract disagreement and every `edit` before relying on
the gate.

## 2a. After your labels are merged: the queue and the evidence

Only after the merge may you open the queue (`tasks/<id>/labels/review_queue.json`,
which contains no verifier outcome; regenerate it with `python
scripts/write_review_queue.py tasks/<id>`) and the recorded evidence, to note where
it disagrees with your label. Do not use the run analysis
(`results/runs/*/analysis.md`) for this: it shows verifier outcomes.

* **The D19 proposal** is the label with labeler
  `builder:refcheck+regression+construction:v1` (labeler kind `model`) in the
  candidate file. Its `note` lists:
  * the failing independent reference checks (written from the reference contract;
    they are *not* the verifiers under evaluation);
  * the failing base repository tests (regression norm);
  * the construction claim.
* **The construction check** is in `tasks/<id>/labels/construction_checks.json`. A
  second agent probed the candidate in the sandbox against the reference solution.
  It records concrete inputs with the candidate's and the reference's outputs, the
  requirements it judged violated, and whether that matches the construction claim.
  Re-run any input you rely on: `tracecontract materialize tasks/<id> <candidate id>
  --out <dir>` writes the candidate's state (it needs the base snapshot), and
  `tracecontract sandbox-python` runs code in it. Do not take the agent's word for it.
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
* Missing requirements, and requirements you would remove or re-classify, and why.
* Candidates where the proposed label was wrong.
* Any session you consider unsuitable (and why) — it goes into the rejection ledger.
