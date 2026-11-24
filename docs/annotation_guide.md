# Annotation guide (v0.4)

v0.4 follows protocol v0.6 §14 (decision log D44). Changes from v0.3: the packet's
session holds the user turns only; candidates with identical diffs share one id; each
reviewer records contract reviews, labels and an origin guess per candidate in one
label file per task; the template is `label_template.json`; reviewer ids are `R` and one
to three digits; every task has two reviewers; a candidate whose reviewers give
different values has no final label until it is adjudicated; and the list of what
reviewers must not open is the one in the packet's README.

Correction (2026-11-21): section 2 described the acceptance gate as it worked before
commit `738493a`, reading only the latest human review of each requirement and counting
`edit` as acceptance. It now states the gate's rules and how the coordinator records a
re-review or an adjudicated contract review (decision log D51, D52). The procedure for
reviewers is unchanged.

Addition (2026-11-24): section 2 now describes `review-packet --strata`, which puts the
held-out candidates of a candidate stratum, such as the fresh attempts of `fresh-v1`
(protocol §15.4), into the packet among each task's own, blinded as they are, and how
`merge-reviews` records their labels where the analysis reads them (decision log D82).
The packet's README, the form of its template and the procedure for reviewers are
unchanged.

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
   An `edit` keeps the requirement out of an accepted task until the contract has been
   changed and the requirement re-reviewed (section 2).
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
still block the acceptance gate (section 2 says how the gate reads the reviews). Without
`--show-candidates` it prints no candidate's origin or label; do not use that option
before your labels have been merged.

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

**Fresh attempts and other candidate strata.** The fresh attempts of `fresh-v1`
(protocol §15.4) are not in `task.json`: they are the candidates of each task's stratum
`fresh-v1` (`tasks/<id>/strata/fresh-v1.json`). `--strata <name>`, given after the
tasks, adds the held-out candidates of the stratum `<name>` of every task to the packet:

```
tracecontract review-packet tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04 --strata fresh-v1 --out <packet> --key <key file> --seed <number>
```

* **Which.** The stratum's held-out candidates (evaluation split, no no-op), and of its
  fresh attempts only those that the analysis keeps. A fresh attempt that every
  analysis excludes (no attempt record, no audit verdict, or an audit that found a read
  of forbidden material) is left out; the key lists it with the reason, and the
  command prints, per stratum, how many candidates it added and how many it left out.
* **Blinded as the task's own.** The stratum's candidates are put among the task's own
  held-out candidates, which are always in the packet with them: one `candidates/`
  folder, one pool of random ids, one shuffled order and one template per task. A
  stratum candidate whose diff is identical to another candidate's, the task's own
  included, shares its id. Nothing in the packet comes from their records: no candidate
  or attempt id, configuration, instruction variant, stratum name or description,
  attempt record, proposal or audit verdict. The `README.md` is the one a packet
  without `--strata` has, and the template has the same form, so no file of the packet
  marks which of its candidates are stratum candidates. It does not hide that it may
  hold some: this section says so, and a task's folder holds more items with them.
* **Refusals.** `review-packet` refuses, and writes nothing, when a task has no such
  stratum, when a stratum breaks its rules (a symbolic link in it, or a candidate id of
  the task's own), or when a task has no held-out candidate of its own, whose folder
  would then show its stratum candidates alone.
* **The key** also records each stratum candidate's stratum, file and patch sha256, so
  that `merge-reviews` can find the file and check it (below).

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
adjudication. The merge does not resolve contract disagreements either.

**Stratum candidates in the merge.** The key says which of the packet's candidates are
stratum candidates and where their files are; the command is the same.
* The merge appends a stratum candidate's reviews to its file in the stratum
  (`tasks/<id>/strata/<name>/candidates/<candidate id>.json`, where an adjudicated label
  goes too). Only the file's `labels` change, and `task.json` and the stratum manifest
  are never written.
* It refuses, before writing anything, if the stratum no longer lists that file, if the
  file holds another patch than the packet showed, or if the stratum breaks its rules.
* A run graded with `tracecontract evaluate --strata` records each stratum candidate's
  file, and `tracecontract analyze` reads the candidate's labels from it; without
  `--allow-proposed-labels` it uses human labels only. `analyze` writes into the run
  directory it is given, so a recorded run such as `results/runs/fresh-v1` is analysed
  in a copy of its `manifest.json` and `results.jsonl`, never in place. Where such an
  analysis is kept is for the repository owner to decide. The recorded analysis of
  `fresh-v1` hashed the stratum's candidate files among its inputs (`meta.inputs`), so
  after a merge they no longer match it.
* No origin guess names a stratum candidate's origin, so the merge does not score the
  guesses on stratum candidates; the right, wrong and unsure counts above are for the
  task's own. It counts each reviewer's guesses on a stratum's candidates by the
  attempt's configuration and instruction variant (`stratum_origin_guesses`, for
  example `config-A/u1`). The counts show whether the guesses differ between the
  attempts that were given the user's correction (`final`) and those that were not
  (`u1`).

**How the acceptance gate reads contract reviews** (`src/tracecontract/contract.py`;
the rules await the owner's confirmation, decision log D51). Only human reviews count;
model and rule reviews are proposals. For each requirement the gate takes each human
reviewer's latest decision and accepts the requirement only if all of them are
`accept`:
* reviewers whose latest decisions differ leave it blocked until an adjudicated review
  is added. From then on the reviews added after the latest adjudicated review decide,
  and while there are none, that adjudicated review alone does;
* `edit` and `needs_discussion` block it until it has been re-reviewed and accepted: a
  later `accept` by each reviewer whose latest decision is not `accept`, or an
  adjudicated `accept`;
* `reject` blocks it.

Every active scored requirement of the reference contract needs this acceptance, and
so does every active scored inferred requirement of any contract. An unresolved
requirement always blocks.

**Recording a re-review or an adjudicated contract review.** `merge-reviews` merges each
packet once and only from complete label files, so the coordinator appends the review by
hand to the requirement's `reviews` list in `tasks/<id>/contracts/reference.json`, after
the merged reviews:

```json
{"reviewer": "human:<id>", "reviewer_kind": "human", "decision": "accept|reject|edit|needs_discussion",
 "timestamp": "<ISO 8601 time with a time zone>", "note": "...", "adjudicated": true}
```

* A re-review by one of the two reviewers uses that reviewer's id
  (`human:<reviewer id>`) and leaves out `"adjudicated": true`.
* An adjudicated review records the decision of a third person or of a discussion, with
  `"adjudicated": true`; its `note` says which reviews it settles and why.
* If an `edit` changes the requirement, the coordinator changes the contract first, and
  the changed requirement is then reviewed again.

Then `tracecontract validate-task tasks/<id>` shows, per contract, which requirements
still block, and `tracecontract accept-task tasks/<id> --dry-run` lists every reason the
gate gives without changing the task.

Contract reviews alone cannot open the gate. It also needs the task's provenance record
(`tasks/<id>/provenance.json`) to be `eligible`, which no command sets; a passed
reconstruction record made from the current files; and every contract the task lists
to pass, the initial-only and full-session contracts included, whose inferred and
unresolved requirements the packet does not show. Recording reviews by hand, like the
merge, writes into a task file that decision log D47 freezes. Whether reviews may be
written there, where the provenance review is recorded, and whether the gate should
check reviews on the condition contracts or on the reference contract only are open
decisions for the repository owner.

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
* **A fresh attempt** (a stratum candidate) has its file in the stratum
  (`tasks/<id>/strata/fresh-v1/candidates/<candidate id>.json`), with its D19 proposal
  and its attempt record (configuration, instruction variant, audit verdict). It has no
  construction check or description, the queue file lists the task's own candidates
  only, and `materialize` reads only those. To run code in an attempt's state, use its
  folder in the packet; the coordinator, who holds the key, can say which one it is.

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
