# Internal review

Three adversarial reviews of the repository and the manuscript, all run on 2026-11-18 by model
agents (Claude, the same model family that built the study). They are not peer review, and no
human has reviewed their findings yet.

## Method

1. **Internal review** of commit `6c1af59`, after the run `pilot-v0.3` (harness 0.3.0) and the
   first full manuscript draft. Six reviewer agents, one per lens (methodology, claims,
   integrity, privacy and rights, security, reproducibility), returned findings with evidence
   and a severity. Each finding went to two skeptic agents told to refute it. The skeptic stage
   was stopped before it finished, to free the host for the final run, so the claims and
   integrity findings and three others have no skeptic verdict or only one. The builder acted
   on every finding, verified or not (decision log D36-D39).
2. **Dispositions review** (12:19-13:46 UTC). For each finding, one read-only agent per lens
   group recorded how it had been resolved, against the repository and its git history, and a
   second agent tried to show that disposition wrong. The builder reviewed both and then fixed
   most of the remaining items (D40-D42). The entries below are the result; the builder's
   changes to an agent's disposition are marked **Builder note**.
3. **Final claims audit** of every public claim and number at commit `787176e` (run
   `pilot-v0.3.1`). Four finder agents (numbers, procedure, consistency, reproducibility),
   one verifier agent per lens and a completeness critic. Findings the verifiers confirmed
   were fixed in the commits that followed `787176e`; the critic's findings are listed at
   the end.

Prompts: `experiments/prompts/workflows/tracecontract-internal-review__*.js`,
`tracecontract-review-dispositions__*.js` and `tracecontract-final-audit__*.js`.

A skeptic verdict of "refuted" means that the skeptic argued the finding is wrong or is not a
defect. Some refuted findings were fixed anyway, for example the two security findings, whose
Docker proofs reproduced.

## Summary

* **Internal review:** 64 findings (3 high, 22 medium, 39 low).
* **Final claims audit:** 69 findings; the verifiers confirmed 65 and rejected 4.

| Internal-review disposition | Findings |
| --- | --- |
| fixed | 48 |
| fixed and disclosed | 10 |
| disclosed | 1 |
| partly fixed | 5 |

## Remaining work and owner decisions

* `methodology:M5`: The verifier specs' generation fields are still unfilled (see R1).
* `methodology:L8`: Minor: the D19 violated list for CS-04-eval-nm-4 still names four requirements, while its construction targets only R-lazy. This changes neither its stratum nor any reported number.
* `claims:M7`: The verifier specs' generation fields are still unfilled (see R1).
* `integrity:M1`: The primary rates still count the duplicated behaviour, as pre-specified; only the exploratory view drops the three candidates.
* `integrity:M2`: The near-miss template in the exported workflow scripts still tells generators to run the repository tests; a new batch should change it.
* `integrity:M4`: There is still no tool-output scan and no private per-agent scratch directory for future runs.
* `integrity:M5`: `frozen_at` is null in all 28 specs; the freeze order rests on git commit times.
* `privacy:P1`: Git history, already pushed, still holds the earlier research notes, the unredacted research prompt (8c13e0c), redaction rules that spell out the owner's context (c830977), original-script hashes in earlier prompt exports, and session ids and session-local paths in earlier generator audit files. Rewriting it needs a force-push and cannot recall copies already fetched: an owner decision. A competing-interests statement is also the owner's call.
* `privacy:P6`: Deleting the third-party session data and other downloads kept outside the repository is an owner decision (listed in STATUS).
* `privacy:P7`: Earlier commits, already pushed, still hold the long-quote versions (owner decision on history; see P1).
* `reproducibility:R1`: The verifier specs' generation fields are still unfilled and not linked to the exported prompts. Agent transcripts and the D17 proposals.json are not published, so third parties cannot re-check the generator audits or the CS-01 contract rebuild; the paper now says so.
* `reproducibility:R6`: The committed pilot-v0.3 analysis.json names 6c1af59 although it was produced by code committed later in 8c13e0c (superseded run; not regenerated).
* `reproducibility:R7`: `tracecontract grade` keeps no log, and the B1 log hashes of pilot-v0.3 and pilot-v0.3.1 cover empty logs.

## Internal-review findings

| ID | Severity | Finding | Skeptics | Disposition |
| --- | --- | --- | --- | --- |
| `methodology:M1` | medium | Zero-width bootstrap intervals presented as 95% intervals for zero-event cells | 1 of 2 refuted | fixed |
| `methodology:M2` | medium | Label rule excludes the near misses verifiers accept; C3/C4 zero false acceptance partly built in | 2 of 2 refuted | fixed and disclosed |
| `methodology:M3` | medium | Exploratory hard-case conclusions unlabeled in abstract and qualitative analysis | 2 of 2 refuted | fixed |
| `methodology:M4` | medium | Pre-specified macro rates missing from human-readable outputs | 0 of 2 refuted | fixed |
| `methodology:M5` | medium | Pre-specified cost, yield and flakiness outcomes dropped without a declared deviation | 0 of 2 refuted | fixed and disclosed |
| `methodology:L1` | low | B1 called least faithful 'on both counts', contradicting the pooled table | 0 of 2 refuted | fixed |
| `methodology:L2` | low | Qualitative analysis misstated outcomes for inflection ambiguous near misses | 0 of 2 refuted | fixed |
| `methodology:L3` | low | Per-family concentration narrative ignored inflection's missing requirement and ambiguous cases | 1 of 2 refuted | fixed |
| `methodology:L4` | low | Audit-effect sentence omitted that four audited verifiers equal their plain versions | 2 of 2 refuted | fixed |
| `methodology:L5` | low | Freeze-order statements and content hash did not cover the CS-04 B1 re-selection | 2 of 2 refuted | fixed |
| `methodology:L6` | low | Harness-reliability agreement mixed in pairs whose verifier changed | 2 of 2 refuted | fixed |
| `methodology:L7` | low | Comparison table reported n = 32 instead of per-metric denominators | not verified (skeptic stage stopped; both runs unfinished) | fixed |
| `methodology:L8` | low | Correction-violating pattern among accepted negatives largely follows from pool design | not verified (skeptic stage stopped) | fixed |
| `methodology:L9` | low | Contradiction-aware coverage rule unlisted in the paper; a contradicted requirement still counts as covered | not verified (skeptic stage stopped) | fixed |
| `methodology:L10` | low | Regression-only negatives would be typed initial-violating | not verified (skeptic stage stopped) | fixed |
| `claims:M1` | medium | Paper called B1 least faithful on both counts despite lower false acceptance | not verified (skeptic stage stopped) | fixed |
| `claims:M2` | medium | Analysis misstated which verifiers accept the plural-acronym near miss | not verified (skeptic stage stopped) | fixed |
| `claims:M3` | medium | Freeze-before-pool claim false for CS-04 B1; hash missed check selection | not verified (skeptic stage stopped) | fixed |
| `claims:M4` | medium | Harness-reliability agreement included pairs whose B1 verifier changed | not verified (skeptic stage stopped) | fixed |
| `claims:M5` | medium | B1 includes session-agent tests, which cause all four B1 false rejections | not verified (skeptic stage stopped) | fixed |
| `claims:M6` | medium | C3/C4 zero false acceptance depends on three disputed valid labels | not verified (skeptic stage stopped) | fixed and disclosed |
| `claims:M7` | medium | Prompts claimed as recorded were absent; promised generation costs not reported | not verified (skeptic stage stopped) | fixed and disclosed |
| `claims:L1` | low | CS-03 alternative 1 said to match the reference on every ASCII probe | not verified (skeptic stage stopped) | fixed |
| `claims:L2` | low | Disputed inflection pre-correction label stated as established fact | not verified (skeptic stage stopped) | fixed |
| `claims:L3` | low | Zero-width bootstrap intervals reported without caveat | not verified (skeptic stage stopped) | fixed |
| `claims:L4` | low | Protocol-specified macro rates, costs, yield and flakiness missing from reports | not verified (skeptic stage stopped) | fixed |
| `claims:L5` | low | Builder correction of a model mapping changes a coverage cell without full disclosure | not verified (skeptic stage stopped) | fixed |
| `claims:L6` | low | Sanitiser over-redacted diff decorators; CS-02 provenance wrong; personal-data statement inaccurate | not verified (skeptic stage stopped) | fixed and disclosed |
| `claims:L7` | low | Reference-contract labelling standard described as more validated than records show | not verified (skeptic stage stopped) | fixed |
| `claims:L8` | low | Sections disagreed on how much of each correction the first request implied | not verified (skeptic stage stopped) | fixed |
| `claims:L9` | low | Ten-minute B1 stall attributed with certainty to the shared-UID defect | not verified (skeptic stage stopped) | fixed |
| `claims:L10` | low | 'Every number' provenance claims exceed what the evidence ledger covers | not verified (skeptic stage stopped) | fixed |
| `claims:L11` | low | Headline isolation statements did not exclude the in-process B1 baseline | not verified (skeptic stage stopped) | fixed |
| `claims:L12` | low | Stale or unsupported statements in STATUS, readiness document and data section | not verified (skeptic stage stopped) | fixed |
| `claims:L13` | low | 'Pre-registered' wording rests only on locally logged timestamps | not verified (skeptic stage stopped) | fixed |
| `integrity:M1` | high | Held-out pool overlaps C4 audit dev attacks; CS-04 anchor duplicated by a near miss | 0 of 1 finished (one skeptic started, did not finish) | fixed and disclosed |
| `integrity:M2` | medium | B1 test files present in near-miss workspaces and run before registration | not verified (skeptic stage stopped) | fixed and disclosed |
| `integrity:M3` | medium | Claims that all verifiers were frozen before the held-out pool are inaccurate | not verified (skeptic stage stopped) | fixed |
| `integrity:M4` | low | Generator audits check tool inputs only; shared scratchpad; incomplete audit records | not verified (skeptic stage stopped) | partly fixed |
| `integrity:M5` | low | Freeze hash omitted the scored check list; specs record no freeze time | not verified (skeptic stage stopped) | fixed |
| `integrity:M6` | low | Near-miss prompt changed between batches despite stated unchanged recipe | not verified (skeptic stage stopped) | fixed and disclosed |
| `privacy:P1` | high | Owner's personal context in tracked research notes and brief | 1 of 2 finished refuted; third not finished | partly fixed |
| `privacy:P2` | high | Redistributed upstream MIT code lacked copyright and permission notices | 0 of 2 refuted | fixed |
| `privacy:P3` | medium | Claim of no third-party personal data in controlled sessions | 0 of 2 refuted | fixed |
| `privacy:P4` | medium | Sanitised transcripts kept harness messages and opaque API fields | 2 of 2 refuted | fixed |
| `privacy:P5` | medium | CS-02 provenance misstated redaction and lacked its source hash | 0 of 2 refuted | fixed |
| `privacy:P6` | medium | Downloads manifest incomplete, including unrecorded third-party session data | 2 of 2 refuted | fixed |
| `privacy:P7` | medium | Long verbatim quotation of a copyrighted company essay in tracked notes | 0 of 2 refuted | partly fixed |
| `privacy:P8` | low | E-mail redaction regex corrupted diff decorator lines and inflated counts | 0 of 2 refuted | fixed |
| `privacy:P9` | low | Session paths and harness ids in tracked notes and label files | 2 of 2 refuted | fixed and disclosed |
| `privacy:P10` | low | Host tool paths in transcripts versus data card statement on sandbox paths | 2 of 2 refuted | disclosed |
| `privacy:P11` | low | Licence summary for grading-image wheels omitted Apache-2.0 and BSD licences | 0 of 2 refuted | fixed |
| `security:SEC-1` | medium | Candidate json.py shadow let the process-separated grader sign forged results | 2 of 2 refuted | fixed and disclosed |
| `security:SEC-2` | low | Runtime-written /work/sitecustomize.py bypassed the static protected-path filter | 2 of 2 refuted | fixed |
| `reproducibility:R1` | medium | Paper said prompts were recorded, but no prompts or generator records were tracked | 0 of 2 refuted | partly fixed |
| `reproducibility:R2` | medium | Image builds called bare python3 -m pip; README omitted prerequisites | 0 of 2 refuted | fixed |
| `reproducibility:R3` | low | README built only CS-01's snapshot before evaluating four tasks | 0 of 2 refuted | fixed |
| `reproducibility:R4` | low | evaluate did not verify the base snapshot hash or record it | 0 of 2 refuted | fixed |
| `reproducibility:R5` | low | Evidence ledger missed sensitivity intervals and caption counts | 0 of 2 refuted | fixed |
| `reproducibility:R6` | low | analysis.json did not record the inputs it was computed from | 1 of 2 refuted | fixed |
| `reproducibility:R7` | low | Grader stdout and stderr were discarded; only an unverifiable hash was kept | 0 of 2 refuted | partly fixed |
| `reproducibility:R8` | low | Documented make -C paper build fails because no Makefile exists | 0 of 2 refuted | fixed |
| `reproducibility:R9` | low | Harbor validation listed as tested could not be reproduced from the repository | 1 of 2 finished, not refuted (second not finished) | fixed |
| `reproducibility:R10` | low | Annotation guide run step needs a state directory no command created | not verified (skeptic stage stopped) | fixed |

### `methodology:M1` (medium): Zero-width bootstrap intervals presented as 95% intervals for zero-event cells

* **Finding:** At 6c1af59 the C3/C4 cells and B2 FR (zero events), plus several paired differences, were printed with [0.00, 0.00] 95% intervals. README and the paper called the intervals wide or said they describe variability.
* **Skeptics:** 1 of 2 refuted
* **Disposition:** fixed. 8c13e0c added Clopper-Pearson intervals and a per-condition degenerate flag. The paper summary table and analysis.md now mark degenerate cells and print exact bounds (0/17 upper 0.20), and results.tex:7, README and STATUS explain degeneracy. Paired comparisons and the HTML report were not changed.
* **Evidence:** `src/tracecontract/metrics.py:112-127`; paper/generated/results_summary.tex (HEAD, C3/C4/B2 rows marked *); `paper/sections/results.tex:7`; `README.md:132-135`; `STATUS.md:103-104`; results/runs/pilot-v0.3/analysis.md (regenerated in 8c13e0c); paper/generated/results_comparisons.tex (six [+0.00, +0.00] rows, unmarked); `src/tracecontract/report.py:66-71`; `paper/sections/protocol.tex:11`; `paper/sections/limitations.tex:10`
* **Builder note:** Checker corrections accepted: five comparison intervals, and the sensitivity table, lacked the mark. Follow-up (D40-D42): degenerate intervals are marked in every table, the analysis and the report; the sensitivity table shows exact intervals; the protocol and limitations sections state the zero-event caveat.

### `methodology:M2` (medium): Label rule excludes the near misses verifiers accept; C3/C4 zero false acceptance partly built in

* **Finding:** At 6c1af59 the D19 rule marked as ambiguous, and so excluded, exactly the near misses most verifiers accept: C3/C4 accept 0/15 confirmed-invalid vs 3/5 ambiguous. The abstract headline was unqualified, and D19 named only the B1 circularity.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed and disclosed. The selection effect remains by design, but it is now reported. A post-hoc cross-tab by D19 status appears in posthoc_table.tex and analysis.md. results.tex:45 names the correlated blind spots and calls the zero rate conditional, and the abstract has an exploratory bullet. The counts match pilot-v0.3: 0/15 vs 3/5, and 21 of 30 ambiguous outcomes are accepts.
* **Evidence:** `paper/sections/results.tex:39-45`; paper/generated/posthoc_table.tex (NM conf./NM amb. columns); `paper/sections/abstract.tex:6-8`; `src/tracecontract/analysis.py:251-257`; docs/decision_log.md:583 (D37); `experiments/protocol.md:216`; `README.md:123-127`; `STATUS.md:97-100`
* **Builder note:** Follow-up (D40-D42): the abstract qualifies the headline inline; the limitations name the shared blind spot of the reference checks and the correction-aware verifiers.

### `methodology:M3` (medium): Exploratory hard-case conclusions unlabeled in abstract and qualitative analysis

* **Finding:** At 6c1af59 abstract.tex:8 and analysis.tex:36-41 drew conclusions about the ambiguous near misses without an exploratory label. One of them was that the headline rates are optimistic.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed. f6c8e9f added '(exploratory)' to the abstract bullet and to the analysis paragraph heading. It also rephrased the optimism conclusion as conditional on the construction claims being correct. The skeptics had argued that the protocol commitment covered only the construction-intent rates; the labels are present either way.
* **Evidence:** `paper/sections/abstract.tex:8`; `paper/sections/analysis.tex:36`; `paper/sections/analysis.tex:42`; commit f6c8e9f

### `methodology:M4` (medium): Pre-specified macro rates missing from human-readable outputs

* **Finding:** At 6c1af59 macro rates, which protocol §6 says are reported alongside pooled rates, appeared only in analysis.json. Under macro FA, B1 (0.383) ranks above C1 (0.367), which reverses the pooled order.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. 8c13e0c added FA and FR macro columns to analysis.md, and the paper summary table now prints macro rates (C1 0.37, C2 0.24, B1 0.38, matching analysis.json). protocol.tex:36 lists them, and protocol v0.4 §12 and D37 record the gap. The HTML report generator was not changed.
* **Evidence:** results/runs/pilot-v0.3/analysis.md (FA macro / FR macro columns); paper/generated/results_summary.tex (HEAD); `paper/sections/protocol.tex:36`; `experiments/protocol.md:222-223`; `docs/decision_log.md:591`; `src/tracecontract/report.py:89-95`
* **Builder note:** Follow-up (D40-D42): the report shows macro rates, exact intervals, the per-family counts behind the macro rates and per-metric denominators.

### `methodology:M5` (medium): Pre-specified cost, yield and flakiness outcomes dropped without a declared deviation

* **Finding:** At 6c1af59 the protocol's cost, yield and audit-repeat flakiness outcomes were neither reported nor logged as deviations. The paper listed a narrower set of secondary measures, and reproducibility.tex claimed prompts were recorded when the repository held none.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed and disclosed. f6c8e9f added a 'Final run and deviations' paragraph (cost not recorded, yield 4 of 4, the three reference repeats agreed) and a 'Costs not recorded' limitation. Workflow scripts and agent prompts are now exported to experiments/prompts, and reproducibility.tex:10 describes them accurately. One TESTGEN template drives C1-C4, so the same-prompt control can now be checked.
* **Evidence:** `paper/sections/protocol.tex:46-48`; `paper/sections/limitations.tex:19`; `paper/sections/reproducibility.tex:10`; `experiments/prompts/workflows/tracecontract-generate__wf_8df267d0-467.js:47`; `src/tracecontract/audit.py:68`; `src/tracecontract/sandbox/docker_runner.py:414-418`; tasks/CS-0*/verifiers/*/spec.json (generation.run_id 'unrecorded')
* **Remaining:** The verifier specs' generation fields are still unfilled (see R1).
* **Builder note:** Follow-up (D40-D42): D42 records the cost deviation; the paper lists all pre-specified secondary measures; protocol v0.5 §13 notes the deviation.

### `methodology:L1` (low): B1 called least faithful 'on both counts', contradicting the pooled table

* **Finding:** At 6c1af59 results.tex:29 said B1 was the least faithful condition on both FA and FR. Its pooled FA (5/17), however, was below C1's (6/17) and tied with C2's.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. f6c8e9f rewrote the sentence: B1 has the highest FR (4/10) and the lowest J, and its FA equals C2's and is below C1's. This matches pilot-v0.3. The old phrase no longer appears in the paper, README or STATUS.
* **Evidence:** `paper/sections/results.tex:33`; paper/generated/results_summary.tex (HEAD); commit f6c8e9f

### `methodology:L2` (low): Qualitative analysis misstated outcomes for inflection ambiguous near misses

* **Finding:** At 6c1af59 analysis.tex:40 said every generated-test condition accepts the plural-acronym near miss. In fact C1 and C2 reject CS-03-eval-nm-4, and C3/C4 reject the other two inflection ambiguous cases.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. f6c8e9f rewrote the bullet: the case is accepted by C3, C4, B2 and B1 and rejected by C1 and C2. It also added that both correction-aware verifiers reject the other two ambiguous inflection near misses. Both statements match the pilot-v0.3 outcome table.
* **Evidence:** `paper/sections/analysis.tex:40`; `paper/sections/analysis.tex:42`; results/runs/pilot-v0.3/analysis.md (CS-03 per-task table); commit f6c8e9f

### `methodology:L3` (low): Per-family concentration narrative ignored inflection's missing requirement and ambiguous cases

* **Finding:** At 6c1af59 results.tex:16-24 said the effect was concentrated in humanize and more-itertools, and that initial-only verifiers 'err little' elsewhere. Yet the inflection initial-only contract misses R-all-caps-input, and C1 accepts most of the inflection ambiguous near misses.
* **Skeptics:** 1 of 2 refuted
* **Disposition:** fixed. f6c8e9f rewrote the paragraph and dropped 'concentrated' and 'err little'. It now says the inflection initial-only contract lacks the all-uppercase requirement, and that C1 and C2 accept two of the three inflection ambiguous near misses. The counts match pilot-v0.3.
* **Evidence:** `paper/sections/results.tex:18-27`; results/runs/pilot-v0.3/analysis.json coverage.CS-03.variants.initial_only; commit f6c8e9f

### `methodology:L4` (low): Audit-effect sentence omitted that four audited verifiers equal their plain versions

* **Finding:** At 6c1af59 the paper, README and STATUS said the audit changed one outcome out of 64. They did not say that four of the eight audited verifiers are byte-identical to their plain versions.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed. The text now says four of the eight audited verifiers needed no revision and are identical, and that the audit changed one of the 32 held-out outcomes of the other four. The manifest hashes and audit iteration counts confirm the four identical pairs. The skeptics had judged the original sentence correct for the pre-specified estimand.
* **Evidence:** `paper/sections/results.tex:29`; `README.md:114-117`; `STATUS.md:95-96`; results/runs/pilot-v0.3/manifest.json (tasks[].verifiers content_sha256); tasks/CS-0*/verifiers/*_audited/spec.json audit.iterations

### `methodology:L5` (low): Freeze-order statements and content hash did not cover the CS-04 B1 re-selection

* **Finding:** At 6c1af59 method.tex:33 and the data card said every verifier was frozen before any held-out candidate existed. CS-04 B1 v2, however, was re-selected after the pool had been graded, and its content hash, which does not cover the check list, did not change.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed. 8c13e0c added checks_sha256 to all 28 frozen specs, and check_frozen now rejects a changed check list. method.tex:33 names the CS-04 B1 exception, and D37 discloses it together with the hash gap.
* **Evidence:** `src/tracecontract/verifier.py:160-186`; `paper/sections/method.tex:33`; `docs/decision_log.md:571`; `docs/decision_log.md:578`; `paper/sections/protocol.tex:19`; `docs/data_card.md:31-32`
* **Builder note:** Checker correction accepted (README and STATUS also lacked the exception). Follow-up (D40-D42): every freeze-order statement carries the CS-04 B1 exception and the pre-correction-state exception; protocol v0.5 §13 and D41 correct the frozen texts.

### `methodology:L6` (low): Harness-reliability agreement mixed in pairs whose verifier changed

* **Finding:** At 6c1af59 results.tex:48 reported that 107 of 108 pairs agree across harness versions. But 9 of those pairs (CS-04 B1) used a different check selection, and the one discordant pair was among them.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed. 8c13e0c made compare_runs.py split pairs by verifier version, content hash and check count. The regenerated comparison gives full agreement on the 99 unchanged-verifier pairs and 8 of 9 on the changed-verifier pairs. The paper text and the reliability table report this split.
* **Evidence:** `scripts/compare_runs.py:38-64`; results/runs/pilot-v0.3/compare_pilot-v0.2.json (pairs_same_verifier 99, pairs_changed_verifier 9); paper/generated/reliability_table.tex (HEAD); `paper/sections/results.tex:69`
* **Builder note:** Checker correction accepted: the pilot-v0.2-h2 row was wrong at c830977 and right only from 3b2b0da. Follow-up (D40-D42): all comparison files were regenerated with the current script, and the table generator refuses comparison files without the changed-verifier split.

### `methodology:L7` (low): Comparison table reported n = 32 instead of per-metric denominators

* **Finding:** At 6c1af59 every paired comparison printed n = 32. FA differences, however, use only the 17 invalid candidates and FR differences only the 10 valid ones.
* **Skeptics:** not verified (skeptic stage stopped; both runs unfinished)
* **Disposition:** fixed. 8c13e0c added n_metric to paired_difference. analysis.md and the paper's comparison table now print 17 for FA and 10 for FR, with a caption that explains n. The HTML report generator still prints n_common.
* **Evidence:** `src/tracecontract/metrics.py:222-224`; paper/generated/results_comparisons.tex (HEAD caption and n column); results/runs/pilot-v0.3/analysis.md (column 'n labeled for metric'); `src/tracecontract/report.py:101`; `src/tracecontract/report.py:106`
* **Builder note:** Follow-up (D40-D42): the report prints the per-metric n.

### `methodology:L8` (low): Correction-violating pattern among accepted negatives largely follows from pool design

* **Finding:** At 6c1af59 the paper and README presented 'every accepted negative violates a correction requirement' as evidence. By design, though, 16 of the 17 invalid candidates are correction-violating.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. The paper, README and STATUS now give the stratum sizes (16 of 17) and say the pattern mostly follows from how the pool was built. results.tex:14 rests the comparison on the C1-C3 discordant pairs. The stratum counts match pilot-v0.3.
* **Evidence:** `paper/sections/results.tex:14-16`; `README.md:102-105`; `STATUS.md:86-88`; results/runs/pilot-v0.3/analysis.md (Accepted negatives by type)
* **Remaining:** Minor: the D19 violated list for CS-04-eval-nm-4 still names four requirements, while its construction targets only R-lazy. This changes neither its stratum nor any reported number.
* **Builder note:** The minor point is disclosed: the paper says the rule's labels record two to six violated requirements for five near misses.

### `methodology:L9` (low): Contradiction-aware coverage rule unlisted in the paper; a contradicted requirement still counts as covered

* **Finding:** At 6c1af59 the paper's v0.3 amendment summary omitted the new coverage rule, and the rule changed no number. It still credited CS-01 initial-only with a requirement that its other requirements contradict (2/4 rather than 1/4).
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. 8c13e0c added covered_but_contradicted to the coverage output (reported, not subtracted), with a unit test. analysis.json lists R-default-unchanged for CS-01 initial-only, and results.tex:66 mentions it. The coverage table caption now states the rule.
* **Evidence:** `src/tracecontract/analysis.py:434-445`; `tests/test_analysis.py:63-70`; results/runs/pilot-v0.3/analysis.json coverage.CS-01.variants.initial_only.covered_but_contradicted; `paper/sections/results.tex:66`; paper/generated/coverage_table.tex (HEAD); `paper/sections/protocol.tex:6`
* **Builder note:** Follow-up (D40-D42): every coverage table shows 'covered but contradicted', and the paper's v0.3 summary lists the coverage rule.

### `methodology:L10` (low): Regression-only negatives would be typed initial-violating

* **Finding:** At 6c1af59 _negative_type returned 'initial_violating' when no violated id mapped to a reference requirement, as with a REGRESSION-only label. No current negative was affected.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. 8c13e0c makes _negative_type return 'unspecified' when no violated id maps to a reference requirement, and adds a unit test for a REGRESSION-only label.
* **Evidence:** `src/tracecontract/analysis.py:87-88`; `tests/test_analysis.py:72-78`; commit 8c13e0c

### `claims:M1` (medium): Paper called B1 least faithful on both counts despite lower false acceptance

* **Finding:** At 6c1af59, results.tex:29 said B1 was the least faithful condition on both false acceptance and false rejection. But B1's pooled false acceptance (5/17) equalled C2's and was below C1's (6/17).
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. The sentence was rewritten in f6c8e9f and refined in 3b2b0da. It now says B1 has the highest false rejection (4/10) and the lowest J, that its pooled FA equals C2's and is below C1's, and that its macro FA is slightly above C1's (0.38 vs 0.37). These match pilot-v0.3 analysis.json, and no 'least faithful' wording remains anywhere.
* **Evidence:** `paper/sections/results.tex:33`; `f6c8e9f`; `3b2b0da`; results/runs/pilot-v0.3/analysis.json conditions.repo_tests / initial_plain / initial_audited

### `claims:M2` (medium): Analysis misstated which verifiers accept the plural-acronym near miss

* **Finding:** At 6c1af59, analysis.tex said every generated-test condition accepts the inflection plural-acronym near miss (CS-03-eval-nm-4), but both initial-only verifiers reject it. results.tex also listed the underscore-acronym near miss (nm-1) among the subtle cases, though C3, C4, B2 and B1 reject it.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. In f6c8e9f, analysis.tex was rewritten. Plural acronyms are now 'accepted by both correction-aware verifiers, B2 and B1, but rejected by both initial-only ones', and the other two ambiguous inflection near misses are said to be rejected by C3 and C4. This matches the outcome matrix and pilot-v0.3 per_task.
* **Evidence:** `paper/sections/analysis.tex:38-42`; `f6c8e9f`; `paper/generated/outcome_matrix.tex:22,25`; `paper/sections/results.tex:39-45`
* **Builder note:** Follow-up (D40-D42): the paper lists all five ambiguous near misses and says which three the correction-aware verifiers accept.

### `claims:M3` (medium): Freeze-before-pool claim false for CS-04 B1; hash missed check selection

* **Finding:** At 6c1af59, the paper and docs said all verifiers were frozen before any held-out candidate existed. But CS-04's evaluated B1 (v2, 777 checks) was frozen on 2026-11-18, after the pool and superseded v1 results existed. v1 and v2 shared one content hash because the hash covered test files only.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. 8c13e0c added a hash of the scored check list (checks_sha256). freeze() records it and check_frozen() enforces it at evaluation. All 28 specs carry it, and it matches their current check lists. method.tex:33 and D37 now name CS-04 B1 v2 as the one exception.
* **Evidence:** `src/tracecontract/verifier.py:160-186`; `src/tracecontract/evaluate.py:83-85`; tasks/CS-04/verifiers/repo_tests/spec.json (version 2, checks_sha256); `paper/sections/method.tex:33`; `docs/decision_log.md:571,579`; `8c13e0c`; `f6c8e9f`
* **Builder note:** Follow-up (D40-D42): the freeze statements carry the exception, and the paper says the superseded B1 v1 results had been seen before v2 was frozen.

### `claims:M4` (medium): Harness-reliability agreement included pairs whose B1 verifier changed

* **Finding:** At 6c1af59, the paper reported 107 of 108 pairs agreeing with a superseded run as harness reliability. But 9 of those pairs, and all 4 pilot-v0.2-h2 pairs, used CS-04 B1 v1 (616 checks) instead of v2 (777), and the one discordant pair was among them. compare_runs.py keyed pairs by verifier id and candidate only.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. 8c13e0c changed compare_runs.py to split pairs by verifier version, content hash and check count. results.tex:69 and the reliability table now report 99/99 on unchanged-verifier pairs and list the 9 changed CS-04 B1 pairs separately (8/9). pilot-v0.2-h2 is shown as 0 unchanged and 4 changed pairs, and STATUS no longer says 107/108.
* **Evidence:** `scripts/compare_runs.py:27-49`; `paper/sections/results.tex:69`; `paper/generated/reliability_table.tex`; `results/runs/pilot-v0.3/compare_pilot-v0.2.json`; `docs/decision_log.md:595`; `8c13e0c`; `f6c8e9f`
* **Builder note:** Follow-up (D40-D42): the pilot-v0.3 comparison files were regenerated with the split.

### `claims:M5` (medium): B1 includes session-agent tests, which cause all four B1 false rejections

* **Finding:** At 6c1af59, the paper called B1 the repository's own tests and said they over-specify the reference. It did not say that the reference is the session agent's final state, that B1 contains tests the agent added, or that all four B1 false rejections come from those tests. It also omitted the D19 caveat that the regression norm shares base tests with B1.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. method.tex:24, results.tex:35, README and STATUS now say three things: the reference is the agent's final state, B1 includes 6-12 agent-added tests per task, and all four false rejections come from those tests. An exploratory upstream-only B1 row (13/17 FA, 0/10 FR) was added using scripts/b1_upstream_checks.py. I confirmed the 6-12 counts, and that every B1 rejection of a valid candidate comes from non-upstream checks.
* **Evidence:** `paper/sections/method.tex:24`; `paper/sections/results.tex:35`; `paper/generated/posthoc_table.tex:10`; `README.md:119-123`; `STATUS.md:94-96`; `tasks/*/verifiers/repo_tests/upstream_check_ids.json`; `docs/decision_log.md:212`; `f6c8e9f`; `8c13e0c`
* **Builder note:** Follow-up (D40-D42): the paper says that upstream-only B1's numbers largely follow from the label rule (it rejects exactly the four invalid candidates that fail the regression norm), and that over-specification comes from the agent-added tests; the data card describes the reference as the agent's final state.

### `claims:M6` (medium): C3/C4 zero false acceptance depends on three disputed valid labels

* **Finding:** At 6c1af59, the paper did not say that C3 and C4 accept all three D19-valid candidates that the independent construction checks judge invalid. Under the check verdicts, C3/C4 false acceptance would be 6/25. Its 'conditional on violations that independent checks can detect' sentence was also inconsistent with this.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed and disclosed. In f6c8e9f, exploratory rates under the construction checks' labels were added to results.tex and the post-hoc table: C3/C4 6/25 with FR 0/7, C1 13/25, B2 8/25, B1 10/25. The text now says C3 and C4 accept all three disputed candidates, and the conditional sentence now refers to 'the labeling checks'. README and STATUS give 6/25. The numbers match pilot-v0.3 sensitivity_check_labels.
* **Evidence:** `paper/sections/results.tex:45`; `paper/sections/results.tex:63`; `paper/generated/posthoc_table.tex`; `README.md:125-128`; `STATUS.md:99-102`; results/runs/pilot-v0.3/analysis.json sensitivity_check_labels
* **Builder note:** Checker correction accepted. Follow-up (D40-D42): the abstract says that C3/C4 accept all three disputed valid-labeled candidates and 6 of 25 under the check labels.

### `claims:M7` (medium): Prompts claimed as recorded were absent; promised generation costs not reported

* **Finding:** At 6c1af59, reproducibility.tex said generated artifacts were recorded with the prompts that produced them. But no prompt text was tracked, and verifier specs had empty prompt hashes and 'unrecorded' run ids. The generation costs promised in protocol §4 were not reported.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed and disclosed. 14 workflow scripts with their prompt templates and 30 standalone agent prompts were exported to experiments/prompts (8c13e0c, with later redaction changes). reproducibility.tex:10 now says where the prompts are, and that full transcripts are kept outside the repository and identified by hash. protocol.tex:48 and limitations.tex:19 now state that costs were not recorded and are not reported.
* **Evidence:** `experiments/prompts/README.md`; `experiments/prompts/agent_prompts.jsonl`; `experiments/prompts/workflows/`; `paper/sections/reproducibility.tex:10`; `paper/sections/protocol.tex:48`; `paper/sections/limitations.tex:19`; `8c13e0c`
* **Remaining:** The verifier specs' generation fields are still unfilled (see R1).

### `claims:L1` (low): CS-03 alternative 1 said to match the reference on every ASCII probe

* **Finding:** At 6c1af59, results.tex and D33 said CS-03 alt-1 and the pre-correction state differ from the reference only on exotic Unicode and match it on every ASCII probe. The construction check records 98 ASCII differences for alt-1, all on apostrophe-joined tokens.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. In f6c8e9f, results.tex was changed to say that alt-1 diverges on exotic Unicode and on some apostrophe-joined ASCII tokens, and that the pre-correction state diverges only on exotic Unicode. This matches tasks/CS-03/labels/construction_checks.json.
* **Evidence:** `paper/sections/results.tex:58-62`; tasks/CS-03/labels/construction_checks.json (CS-03-eval-alt-1 evidence); `docs/decision_log.md:468-470`; `f6c8e9f`
* **Builder note:** Checker correction accepted. Follow-up (D40-D42): D41 corrects D33; the analysis section names the dotted İ and circled capitals.

### `claims:L2` (low): Disputed inflection pre-correction label stated as established fact

* **Finding:** At 6c1af59, the README, results.tex and the abstract said the inflection pre-correction state already satisfied the correction, i.e. is valid. That is only the D19 proposal, and the independent check judges it invalid.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. f6c8e9f removed the claim from results.tex. The abstract now says 'the rule labels two of the four pre-correction states valid, and an independent check disputes one of them'. analysis.tex:27 now says the rule labels it valid and the independent check disputes that label.
* **Evidence:** `paper/sections/abstract.tex:9`; `paper/sections/analysis.tex:27`; `paper/sections/results.tex:26`; `README.md:113-114`; `f6c8e9f`
* **Builder note:** Follow-up (D40-D42): the README qualifies the inflection label.

### `claims:L3` (low): Zero-width bootstrap intervals reported without caveat

* **Finding:** At 6c1af59, the summary and comparison tables printed [0.00, 0.00] 95% intervals for zero-event rates and differences, while the README said the intervals were wide. No caveat or exact bound was given.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. 8c13e0c added degeneracy flags and exact (Clopper-Pearson) intervals to the analysis, and f6c8e9f put them in the paper. The summary table marks degenerate intervals with * and prints exact bounds (upper 0.20 for 0/17, 0.31 for 0/10). results.tex:7 explains the convention, and the README notes the degeneracy.
* **Evidence:** `paper/generated/results_summary.tex`; `paper/sections/results.tex:7`; `paper/make_tables.py:104-106`; `README.md:132-136`; `paper/generated/results_comparisons.tex:9-15`; `paper/generated/sensitivity_table.tex:6-8`
* **Builder note:** Follow-up (D40-D42): degenerate intervals are marked in every table.

### `claims:L4` (low): Protocol-specified macro rates, costs, yield and flakiness missing from reports

* **Finding:** At 6c1af59, measures named in protocol §4 and §6 were neither reported nor logged as deviations: macro rates, generation costs, task yield, verifier flakiness and cost per accepted task. Macro FA reverses the B1 vs C1 ordering.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. Macro rates were added to the paper's summary table and to pilot-v0.3 analysis.md. The results text now gives the macro B1-vs-C1 ordering next to the pooled one (8c13e0c, f6c8e9f, 3b2b0da). The paper's protocol section now says costs were not recorded and gives yield (4 of 4) and audit-repeat agreement. The limitations section repeats the cost gap. Audit records show no unresolved reference repeats.
* **Evidence:** `paper/generated/results_summary.tex:4-9`; `paper/sections/results.tex:33`; `paper/sections/protocol.tex:48`; `paper/sections/limitations.tex:19`; `results/runs/pilot-v0.3/analysis.md:13`; `src/tracecontract/report.py:89-95`; `docs/decision_log.md:591`; `experiments/protocol.md:222`
* **Builder note:** Checker corrections accepted. Follow-up (D40-D42): the report shows macro rates and per-metric n; D42 records the cost deviation; the yield wording says none is accepted yet.

### `claims:L5` (low): Builder correction of a model mapping changes a coverage cell without full disclosure

* **Finding:** At 6c1af59, the CS-01 full-session mapping carried a builder correction that removed one contradicts claim. This set the coverage table's Contradicting cell to 0 instead of 1. No document mentioned it.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. f6c8e9f added a sentence to the paper: one mapper-1 contradiction claim was corrected after a sandbox check showed a wrong assumption about base behaviour. The correction and its reason remain in the mapping file's corrections field. I confirmed that without it the Contradicting cell would be 1. The reported kappa uses the map field only and is unaffected.
* **Evidence:** `paper/sections/results.tex:66`; tasks/CS-01/contracts/mapping_full_session.json (corrections); `src/tracecontract/analysis.py:436`; `src/tracecontract/analysis.py:512`; `paper/generated/coverage_table.tex:2`; `docs/data_card.md:50-51`
* **Builder note:** Follow-up (D40-D42): D42 records the correction and its effect (one contradicting requirement fewer); the coverage caption and the results text say the builder made it.

### `claims:L6` (low): Sanitiser over-redacted diff decorators; CS-02 provenance wrong; personal-data statement inaccurate

* **Finding:** At 6c1af59, the e-mail regex corrupted '+@pytest...' decorator lines in two published transcripts. The CS-02 provenance record said no redaction was needed and had no sanitisation record. The paper said there was no third-party personal data, although public upstream maintainer names appear in tool output.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed and disclosed. 8c13e0c added sanitize:v2, which needs a letter or digit after leading diff markers. It re-sanitised all four transcripts and corrected the provenance records, including CS-02. D38 records this. c830977 and 3b2b0da reworded the ethics section and data card: public upstream names and handles are kept as attribution, and e-mails are redacted. I checked the regex on decorator strings, both lines (intact), the hashes (they match provenance) and that each transcript has one real redaction.
* **Evidence:** `src/tracecontract/ingest/claude_code.py:235-251`; `data/controlled/transcripts/CS-01.jsonl:170`; `data/controlled/transcripts/CS-02.jsonl:155`; tasks/CS-02/provenance.json (redaction_status, transcript_sanitization); `docs/decision_log.md:598-614`; `paper/sections/ethics.tex:5`; `docs/data_card.md:86-98`
* **Builder note:** Checker correction accepted. Follow-up (D40-D42): the provenance hashes and the task builder's code cause are fixed (see P3-P5).

### `claims:L7` (low): Reference-contract labelling standard described as more validated than records show

* **Finding:** At 6c1af59, the paper called the reference contract ground truth operationalised with exact quotes. It omitted that the contract is model-reviewed only and that CS-01's was written after U1 output was seen. One CS-04 requirement is inferred with no quote. Five near misses violate more than one requirement, although the documents say each violates one.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. f6c8e9f rewrote the paper's Labels paragraph. It now says 'labeling standard' and 'model-reviewed only', that humanize was operationalised after the first output was seen, and that one more-itertools requirement is inferred without a quote. I confirmed the inferred CS-04 requirement and the multi-requirement label records.
* **Evidence:** `paper/sections/protocol.tex:26`; `README.md:42`; `paper/sections/introduction.tex:24`; `docs/data_card.md:39`; `paper/sections/protocol.tex:17`; tasks/CS-04/contracts/reference.json (R-default-unchanged: inferred, no evidence); tasks/CS-04/candidates/CS-04-eval-nm-3.json (6 violated requirements)
* **Builder note:** Checker correction accepted. Follow-up (D40-D42): the README, introduction, data card, protocol section, limitations and controlled-data README are corrected; D41 notes the frozen texts.

### `claims:L8` (low): Sections disagreed on how much of each correction the first request implied

* **Finding:** At 6c1af59, results and STATUS said 'every' tinydb correction requirement was inferred, while analysis and limitations said 'most'. Results limited information-carrying corrections to two families, although inflection's initial-only contract lacks R-all-caps-input, the requirement behind C1's one inflection false acceptance.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. f6c8e9f aligned the results, analysis and limitations sections on 'requirements covering everything the correction later stated' (coverage 6/6). Results now says the inflection initial-only contract lacks the all-uppercase requirement and that C1 accepts the near miss that breaks it. STATUS ('inferred the whole correction') is consistent with this. I checked pilot-v0.3 coverage and outcomes.
* **Evidence:** `paper/sections/results.tex:18-27`; `paper/sections/analysis.tex:18`; `paper/sections/limitations.tex:7`; `STATUS.md:103-104`; results/runs/pilot-v0.3/analysis.json (coverage.CS-03 initial_only missing R-all-caps-input)
* **Builder note:** Checker correction accepted. Follow-up (D40-D42): the analysis section says the agent's state already met the correction.

### `claims:L9` (low): Ten-minute B1 stall attributed with certainty to the shared-UID defect

* **Finding:** At 6c1af59, the results section attributed the one discordant reliability pair (CS-04 B1 alt-1) to the shared-UID defect. The method section blamed stalls on the address-space/arena defect, and D30 lists this pair among stalls fixed by 0.3.0.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. f6c8e9f replaced the sentence with the suggested wording: 'the pair that the harness resource-limit defects turned into a ten-minute stall (D28-D30)'. It also says the pair's verifier changed (D31). No tracked file still attributes the stall to the shared UID.
* **Evidence:** `paper/sections/results.tex:69`; `paper/sections/method.tex:46-50`; `docs/decision_log.md:409-427`; `results/runs/pilot-v0.3/compare_pilot-v0.2.md`

### `claims:L10` (low): 'Every number' provenance claims exceed what the evidence ledger covers

* **Finding:** At 6c1af59, the ethics section, paper/README.md and the results section said every number came from recorded runs and was listed in the evidence ledger. The ledger lists only generated-table numbers, and several prose numbers come from elsewhere.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. f6c8e9f narrowed the ethics claim to 'every number in the paper's tables' and added that text numbers repeat table values or decision-log counts. Results now says the ledger lists the numbers in the tables. Spot checks: prose counts such as 78 transcripts, the 30/30 vs 2/30 threads and about 21 threads are in D26 and D29.
* **Evidence:** `paper/sections/ethics.tex:22`; `paper/sections/results.tex:3`; `paper/sections/results.tex:5`; `paper/README.md:8-9`; `paper/sections/introduction.tex:25`; `paper/evidence_ledger.md:3`
* **Builder note:** Follow-up (D40-D42): the 'every number' wording is narrowed in paper/README.md, the introduction, the results section and the ethics section.

### `claims:L11` (low): Headline isolation statements did not exclude the in-process B1 baseline

* **Finding:** At 6c1af59, the README and abstract described process-separated grading with tested isolation. They did not say that B1 (repository tests) runs candidate code in the reporting process. That exception appeared only in later sections.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. c830977 limited the README grading bullet to C1-C4 and B2 and added an explicit B1 exception. f6c8e9f changed the abstract: the generated-test verifiers grade in the sandbox, and the repository-test baseline runs in-process.
* **Evidence:** `README.md:47`; `README.md:56-58`; `paper/sections/abstract.tex:4`; `paper/sections/ethics.tex:19-20`; `paper/sections/limitations.tex:21`
* **Builder note:** Follow-up (D40-D42): the introduction now counts the defects correctly.

### `claims:L12` (low): Stale or unsupported statements in STATUS, readiness document and data section

* **Finding:** At 6c1af59, four statements were stale or unsupported. STATUS cited D1-D34 although D35 existed. The readiness document named the wrong closest work and claim scope. STATUS stated an unconfirmed nftables cause for the Harbor no-network failure as fact. The data section said the correction-framing deviation is recorded with each task, but it is only in D10 and the data README.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. c830977 updated STATUS to D1-D39. It also rewrote readiness item 4 to name SessionFarmer and the D34 combination claim, matching related.tex.
* **Evidence:** `STATUS.md:55`; `docs/submission_readiness.md:19-26`; `STATUS.md:115-117`; `docs/research/notes/harbor.md:398`; `docs/decision_log.md:216-224`; `paper/sections/data.tex:18`; tasks/CS-01/task.json (notes empty); `data/controlled/README.md:14-17`
* **Builder note:** Checker correction accepted. Follow-up (D40-D42): the STATUS nftables wording, the data section's deviation wording and the Harbor docstring are corrected.

### `claims:L13` (low): 'Pre-registered' wording rests only on locally logged timestamps

* **Finding:** At 6c1af59, the README, STATUS and the paper called the scenarios and intended requirements pre-registered. The CS-02 to CS-04 hashes first appear in git after the CS-04 session ended, so 'before the run' rests only on the decision log.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. c830977 and f6c8e9f replaced the term with 'hashed and logged locally before each session ran (not a formal preregistration)'. This covers the README, STATUS and the paper's protocol and data sections. I confirmed the timing: the CS-04 scenario hash first appears in cbb8dcd at 02:14:43Z, and that session's last event is at 02:11:49Z.
* **Evidence:** `README.md:58-60`; `STATUS.md:23-25`; `STATUS.md:33-35`; `paper/sections/protocol.tex:26`; `paper/sections/data.tex:11`; `data/controlled/README.md:11`
* **Builder note:** Checker correction accepted. Follow-up (D40-D42): the controlled-data README and data card explain the legacy label; new builds write `study-design:hashed-scenario`; protocol v0.5 §13 and D41 correct the frozen texts.

### `integrity:M1` (high): Held-out pool overlaps C4 audit dev attacks; CS-04 anchor duplicated by a near miss

* **Finding:** CS-04-eval-nm-2 and CS-04-pre-correction have the same graded patch as CS-04 dev attack a3, and CS-01-eval-nm-5 differs from CS-01 dev attack a3 only in one docstring line. Both a3 attacks were in the C4 audit sets. Nothing disclosed this, and the brief said evaluation candidates are never used in an audit.
* **Skeptics:** 0 of 1 finished (one skeptic started, did not finish)
* **Disposition:** fixed and disclosed. D37, protocol v0.4 section 12, the paper (protocol, results, limitations) and the README now disclose the CS-04 pair and say that C4's audit made no revision. analysis.py flags exact graded-patch duplicates and adds an exploratory rate without them (C1 4/15, C4 0/15). Preflight warns when a held-out patch equals a dev patch. The pool and the primary counts are unchanged.
* **Evidence:** `docs/decision_log.md:557`; `paper/sections/protocol.tex:23`; `paper/sections/results.tex:51-56`; `paper/sections/limitations.tex:15`; `experiments/protocol.md:205`; `README.md:129`; `src/tracecontract/analysis.py:266-293`; `scripts/preflight_final_run.py:62-68`; `results/runs/pilot-v0.3/analysis.md:100-103`; tasks/CS-01/candidates/CS-01-eval-nm-5.json vs tasks/CS-01/candidates/CS-01-dev-attack-full_session-a3.json (only a docstring line in src/humanize/filesize.py differs); `docs/research_brief.md:387`; commit 8c13e0c; commit 3f38b47; commit f6c8e9f
* **Remaining:** The primary rates still count the duplicated behaviour, as pre-specified; only the exploratory view drops the three candidates.
* **Builder note:** Checker corrections accepted. Follow-up (D40-D42): CS-01-eval-nm-5 is detected (same code apart from one docstring line; `scripts/find_duplicates.py`) and disclosed; the 'one frozen held-out pool' wording is qualified; the preflight compares held-out patches with each other and checks the same-code record.

### `integrity:M2` (medium): B1 test files present in near-miss workspaces and run before registration

* **Finding:** Near-miss workspaces received the full reference diff. Its test hunks are B1's test files, and the generators ran them on near misses before registering them. The paper said the workspaces contained no verifier files.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed and disclosed. D37 and protocol v0.4 section 12 record that near-miss workspaces held B1's tests and that the generators ran them. The paper now says 'isolated workspaces' instead of 'no verifier files' and lists this exception. It states that B1's outcomes on near misses are not blind to construction. README limitations say the same. The near misses were not regenerated. A check confirmed that every test line the reference patch adds is in B1's overlay.
* **Evidence:** `docs/decision_log.md:563`; `paper/sections/protocol.tex:19-21`; `paper/sections/results.tex:36`; `paper/sections/limitations.tex:14`; `experiments/protocol.md:206`; `README.md:255`; `src/tracecontract/cli.py:356`; commit 3f38b47; commit f6c8e9f
* **Remaining:** The near-miss template in the exported workflow scripts still tells generators to run the repository tests; a new batch should change it.
* **Builder note:** Checker corrections accepted. Follow-up (D40-D42): the stale statements are corrected (brief, data card, STATUS; protocol and D14 via v0.5 §13 and D41); `export-gen-workspace` leaves the reference's test hunks out by default.

### `integrity:M3` (medium): Claims that all verifiers were frozen before the held-out pool are inaccurate

* **Finding:** The paper, protocol, data card and README said every verifier was frozen before any held-out candidate existed. In fact the CS-01 and CS-04 reference checks were written while the pool was being generated, the CS-02 reference checks were revised after it, CS-04 B1 v2 was frozen after it, and the pre-correction states pre-date all verifiers.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. method.tex now limits the claim to the evaluated verifiers (C1-C4, B1, B2) and names the CS-04 B1 exception (D31). protocol.tex and limitations.tex say the reference checks were written concurrently with, or after, the pool, without access to it. D37 and protocol section 12 record the timing. Git freeze commits confirm that C1-C4, B2 and B1 v1 were frozen before the first generated candidate of each task.
* **Evidence:** `paper/sections/method.tex:33`; `paper/sections/protocol.tex:28`; `paper/sections/limitations.tex:16`; `docs/decision_log.md:567`; `experiments/protocol.md:207`; `README.md:257`; `docs/data_card.md:31-33`; `README.md:30`; `docs/research_brief.md:387`; commit f6c8e9f
* **Builder note:** Checker corrections accepted: more places made the claim, and CS-02's checks were written concurrently, not after. Follow-up (D40-D42): every freeze statement is qualified, the pre-correction state is named as captured before the verifiers, and D41 gives the reference-check timing.

### `integrity:M4` (low): Generator audits check tool inputs only; shared scratchpad; incomplete audit records

* **Finding:** The generator audit matches forbidden substrings in tool inputs only. Tool outputs and a shared, agent-visible scratchpad showed held-out file names to some label-instrument agents. The audit records lack transcript paths and forbidden/allowed lists, and the CS-03/CS-04 refcheck entries have no transcript hash.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** partly fixed. D37, protocol.tex:19 and limitations.tex:17 now say that the audit inspects tool inputs only, that some tool outputs (a git status listing) showed held-out file names to fix agents, and that agents shared a scratch directory. The audit code still scans inputs only. generator_audit.json only gained redaction of session ids and paths.
* **Evidence:** `docs/decision_log.md:575`; `paper/sections/protocol.tex:19`; `paper/sections/limitations.tex:17`; `src/tracecontract/controlled.py:185-216`; scripts/audit_eval_generators.py (only redaction added, c830977/3b2b0da); `tasks/CS-03/labels/generator_audit.json`; `tasks/CS-04/labels/generator_audit.json`; `experiments/prompts/agent_prompts.jsonl`
* **Remaining:** There is still no tool-output scan and no private per-agent scratch directory for future runs.
* **Builder note:** Checker corrections accepted. Follow-up (D40-D42): the audit records state their rules and their inputs-only scope; the CS-03/CS-04 reference-check records name their writers' transcripts; D41 adds the shared-scratch facts; STATUS, the data card and D41 carry the inputs-only caveat.

### `integrity:M5` (low): Freeze hash omitted the scored check list; specs record no freeze time

* **Finding:** content_sha256 hashed only the test files, so B1's scored check selection in spec.json was unprotected, and validate-task matched B1 v1 and v2 alike. Specs had no freeze time, run id or prompt hash, so freeze order rested on git commit times.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. Specs now carry checks_sha256 (sorted check ids with their requirement ids). It was backfilled for all 28 frozen specs, and all 28 match a recomputation. freeze() now records frozen_at. check_frozen, which evaluate calls, rejects a changed check list. Run manifests record checks_sha256 and n_checks. method.tex:33 and D37 describe the change.
* **Evidence:** `src/tracecontract/verifier.py:160-186`; `src/tracecontract/evaluate.py:83-85`; `src/tracecontract/schemas.py:442-443`; `docs/decision_log.md:578`; `paper/sections/method.tex:33`; `src/tracecontract/cli.py:200`; commit 8c13e0c
* **Remaining:** `frozen_at` is null in all 28 specs; the freeze order rests on git commit times.
* **Builder note:** Checker corrections accepted. Follow-up (D40-D42): validate-task checks the check-list hash, `check_frozen` requires it, `freeze` refuses to re-freeze, run comparison uses the hash when both manifests record it, and the paper says the hash was added after pilot-v0.3.

### `integrity:M6` (low): Near-miss prompt changed between batches despite stated unchanged recipe

* **Finding:** The CS-01/CS-02 near-miss prompt added a repository-test step and a 'finish one near miss before the next' instruction, compared with CS-03/CS-04. D33 and protocol section 11 still said the recipe was unchanged.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed and disclosed. D37 records the prompt change, and the paper's protocol section lists it as a disclosed exception. The prompts are exported with hashes: agent_prompts.jsonl has the CS-03/CS-04 near-miss prompts, and the CS-01/CS-02 workflow script headers give the script sha256. The template in the exported script shows both added lines.
* **Evidence:** `docs/decision_log.md:572`; `paper/sections/protocol.tex:22`; `experiments/prompts/agent_prompts.jsonl`; `experiments/prompts/workflows/tracecontract-heldout__wf_2c429631-ebb.js:1`; `experiments/prompts/workflows/tracecontract-heldout__wf_2c429631-ebb.js:53-55`; `experiments/protocol.md:196`; `docs/decision_log.md:452`
* **Builder note:** Checker corrections accepted. Follow-up (D40-D42): D41 lists the prompt differences and corrects D33; the export marks the stopped attempts and gives each run's start and finish.

### `privacy:P1` (high): Owner's personal context in tracked research notes and brief

* **Finding:** At 6c1af59, tracked research notes and the brief held personal context of the repository owner: material from a company's pages other than its essay, and a mapping of the project onto that material. The paper had no competing-interests statement.
* **Skeptics:** 1 of 2 finished refuted; third not finished
* **Disposition:** partly fixed. c830977 removed the material and the mapping from the research note and the brief. Both now rely on the public essay, and use the homepage and sitemap only to check that no other essay exists. c830977 also redacted the exported research prompt, and c37b941 (a commit after the four listed) moved the owner-specific redaction rules out of the repository. A grep of tracked files at HEAD finds no remaining markers.
* **Evidence:** `docs/research/notes/sfdata.md:4-7`; `docs/research/notes/sfdata.md:15-19`; `docs/research_brief.md:34`; `scripts/export_prompts.py:11-16`; `scripts/export_prompts.py:43-54`; `STATUS.md:122-126`; `paper/main.tex:19`; commit c830977; commit c37b941
* **Remaining:** Git history, already pushed, still holds the earlier research notes, the unredacted research prompt (8c13e0c), redaction rules that spell out the owner's context (c830977), original-script hashes in earlier prompt exports, and session ids and session-local paths in earlier generator audit files. Rewriting it needs a force-push and cannot recall copies already fetched: an owner decision. A competing-interests statement is also the owner's call.
* **Builder note:** Checker correction accepted: the remote was already at 787176e, so this material is pushed. STATUS lists it as an owner decision.

### `privacy:P2` (high): Redistributed upstream MIT code lacked copyright and permission notices

* **Finding:** At 6c1af59, about 27k lines of upstream MIT code (test overlays, copied tests, patch context, transcript excerpts) were tracked with no MIT notice. The data card and paper said attribution by URL and commit was enough.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. c830977 added THIRD_PARTY_LICENSES/ with the four upstream licence files. Each is byte-identical to the file at the pinned commit (checked with git show piped to cmp). Its README maps every path to its project, and I confirmed that the overlays only add lines to the upstream files. The data card, the paper and the README now point to it.
* **Evidence:** `THIRD_PARTY_LICENSES/README.md:1-41`; `THIRD_PARTY_LICENSES/tinydb.txt:1`; `docs/data_card.md:66-73`; `paper/sections/ethics.tex:7`; `README.md:270`; commit c830977
* **Builder note:** Checker corrections accepted: the notices are already on the remote, and the path map understated the CS-03 copy. Follow-up (D40-D42): the path map now lists every verifier file that embeds upstream code.

### `privacy:P3` (medium): Claim of no third-party personal data in controlled sessions

* **Finding:** At 6c1af59, the data card, the paper and a code comment said controlled sessions contain no third-party personal data. The transcripts carry upstream maintainers' public names, and their e-mail addresses had been redacted.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. The data card (c830977) and the paper (f6c8e9f) now say that names are kept as attribution and e-mail addresses are redacted. The stated counts match the transcripts. All four provenance records now say redacted_by_us.
* **Evidence:** `docs/data_card.md:83-89`; `paper/sections/ethics.tex:5`; `tasks/CS-02/provenance.json:19`; `src/tracecontract/schemas.py:504`; `src/tracecontract/tasks.py:189`
* **Builder note:** Checker correction accepted: CS-01 line 42 holds repositories under three personal accounts. Follow-up (D40-D42): the schema marks `not_needed_controlled` as legacy, the task builder records `redacted_by_us` with its sanitisation record, and the data card counts are corrected.

### `privacy:P4` (medium): Sanitised transcripts kept harness messages and opaque API fields

* **Finding:** At 6c1af59, every transcript kept a harness meta reminder at line 2, opaque thinking-block signatures (64% of the bytes) and caller fields on all tool calls. The data card said harness internals were removed.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed. 8c13e0c added sanitize:v2. It drops signature and caller fields and blanks harness meta messages, while keeping the scripted turns. The transcripts were re-sanitised: no signature or caller field is left, and line 2 is now a placeholder. My in-memory re-run from the raw transcripts reproduced all four files byte for byte. D38 records the change, and a unit test covers it.
* **Evidence:** `src/tracecontract/ingest/claude_code.py:236`; `src/tracecontract/ingest/claude_code.py:261`; `src/tracecontract/ingest/claude_code.py:302-307`; `tests/test_ingest_contract.py:196-221`; `docs/decision_log.md:598-614`; commit 8c13e0c
* **Builder note:** Follow-up (D40-D42): the top-level `trace_sha256` names the published transcripts (superseded hashes kept under `previous`); the data card and the paper say the thinking text is kept (178 blocks, 111 empty).

### `privacy:P5` (medium): CS-02 provenance misstated redaction and lacked its source hash

* **Finding:** At 6c1af59, CS-02's provenance said not_needed_controlled and had no sanitisation record or original-transcript hash, although its transcript had been redacted. The cause was hard-coded in tasks.py.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. 8c13e0c set CS-02 and its index entry to redacted_by_us. It also added a transcript_sanitization record whose source hash matches the raw transcript on disk. D38 records the correction.
* **Evidence:** `tasks/CS-02/provenance.json:19`; `tasks/CS-02/provenance.json:25`; `data/manifests/provenance_index.json:40`; `docs/decision_log.md:612-614`; `src/tracecontract/tasks.py:189`; `src/tracecontract/tasks.py:192-193`
* **Builder note:** Follow-up (D40-D42): the task builder records its sanitisation; the provenance hashes are corrected (see P3, P4).

### `privacy:P6` (medium): Downloads manifest incomplete, including unrecorded third-party session data

* **Finding:** At 6c1af59, the downloads manifest had 8 records with no sizes, and two of them had no licence. Many documented downloads were missing, including a fetched copy of a third party's agent-session data with no retention record.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed. c830977 rebuilt the manifest with 66 records. Each has source, version, licence, size, purpose, retention, in_repo and a personal-data field. The third-party session data has its own record and a note in the research notes. Two sizes I spot-checked match du -sb.
* **Evidence:** `data/manifests/third_party_downloads.json:4`; `data/manifests/third_party_downloads.json:11`; `data/manifests/third_party_downloads.json:611`; `docs/research/notes/swechat.md:275`; commit c830977
* **Remaining:** Deleting the third-party session data and other downloads kept outside the repository is an owner decision (listed in STATUS).
* **Builder note:** Checker correction accepted: the re-fetched arXiv help pages had no record. Follow-up (D40-D42): the manifest now records them and its scope note covers the submission notes.

### `privacy:P7` (medium): Long verbatim quotation of a copyrighted company essay in tracked notes

* **Finding:** At 6c1af59, a tracked note reproduced about 42-45% of a company essay that states no open licence, and the brief reproduced about 20%. The paper quotes one sentence.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** partly fixed. c830977 trimmed both files to one quoted sentence and one quoted phrase, and paraphrased the rest. My 8-word overlap check against the downloaded essay gives 5.5% for the note (title lines included) and 2.9% for the brief, down from 44.9% and 20.2%.
* **Evidence:** `docs/research/notes/sfdata.md:7`; `docs/research_brief.md:34`; `STATUS.md:122-126`; commit c830977
* **Remaining:** Earlier commits, already pushed, still hold the long-quote versions (owner decision on history; see P1).
* **Builder note:** Checker: overlap at HEAD is 2.7% and 1.9%, no tracked file above 2.7%.

### `privacy:P8` (low): E-mail redaction regex corrupted diff decorator lines and inflated counts

* **Finding:** At 6c1af59, the redaction regex matched '+@decorator' diff lines and altered two published diffs. CS-01's provenance and D21 counted two e-mail addresses where only one was real.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. 8c13e0c changed the redactor: a local part now needs a letter or digit after any leading diff markers. It also added a unit test with diff lines and re-sanitised the transcripts. Both diffs are intact again, no address-like string remains, and provenance records one e-mail per transcript (CS-01 keeps its previous count). D38 corrects D21, which stays as written in the append-only log.
* **Evidence:** `src/tracecontract/ingest/claude_code.py:240-251`; `tests/test_ingest_contract.py:209-221`; `data/controlled/transcripts/CS-01.jsonl:170`; `data/controlled/transcripts/CS-02.jsonl:155`; `docs/decision_log.md:598-611`; commit 8c13e0c
* **Builder note:** Checker correction accepted. Follow-up (D40-D42): D41 corrects D21's counts.

### `privacy:P9` (low): Session paths and harness ids in tracked notes and label files

* **Finding:** At 6c1af59, three research notes and three generator audits held the session scratchpad path and session id. The construction-check sources held harness workflow and agent ids.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed and disclosed. c830977 replaced the paths and the session id with <scratchpad> and <session>, and relabelled the construction-check sources with study-local names. No tracked file at HEAD contains the session id or the scratchpad path.
* **Evidence:** `docs/research/notes/corrections.md:4`; `tasks/CS-01/labels/generator_audit.json:41`; `tasks/CS-01/labels/construction_checks.json:13`; `experiments/prompts/agent_prompts.jsonl:1-30`; `experiments/prompts/workflows/`; commit c830977
* **Builder note:** Checker correction accepted: workflow and agent ids are kept as provenance keys (disclosed in the data card). Follow-up (D40-D42): `scripts/scan_tracked_files.py` scans every file git would publish (credentials, session paths, e-mail addresses, private markers) and is run before each push.

### `privacy:P10` (low): Host tool paths in transcripts versus data card statement on sandbox paths

* **Finding:** At 6c1af59, the data card said that paths in transcripts refer to the study's sandbox. Two tool results list host tool locations under /root/.local/bin.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** disclosed. c830977 reworded the data card. It now says transcript paths refer to sandbox workspaces, temporary files and standard system locations, and it names the two exceptions (CS-01 line 107, CS-04 line 43). The paths are still in the transcripts at those lines, and all home-directory paths are under the study's workspaces.
* **Evidence:** `docs/data_card.md:90-93`; `data/controlled/transcripts/CS-01.jsonl:107`; `data/controlled/transcripts/CS-04.jsonl:43`; commit c830977
* **Builder note:** Checker: only the pointer was stale.

### `privacy:P11` (low): Licence summary for grading-image wheels omitted Apache-2.0 and BSD licences

* **Finding:** At 6c1af59, ownership_and_defense.md summed up the grading-image wheels as MIT/MPL-2.0. Several wheels that the exporter copies are Apache-2.0, BSD-2-Clause or BSD-3-Clause.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. c830977 replaced the summary row with one row per wheel, giving each licence as its METADATA declares it and the images that use it. I read the METADATA of every wheel in the three cached wheelhouses, and all 12 rows match. The manifest's wheelhouse records carry the same licences.
* **Evidence:** `docs/ownership_and_defense.md:13-24`; `docs/ownership_and_defense.md:30-34`; `data/manifests/third_party_downloads.json:260-330`; commit c830977

### `security:SEC-1` (medium): Candidate json.py shadow let the process-separated grader sign forged results

* **Finding:** At 6c1af59 sandbox children started without -I, with the candidate directory ahead of the stdlib. A candidate json.py replaced the wrapper's serialiser, which signed the forged payload, and a wrong candidate got reward 1.0 in a Docker proof.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed and disclosed. Harness 0.3.1 (8c13e0c, D36) starts children with -s -S -P. The wrapper now removes candidate paths before importing json, hmac, hashlib and traceback. A json.py Docker regression probe was added, and D36, the paper and STATUS describe the defect and say candidate code still controls its own report within one call.
* **Evidence:** `src/tracecontract/sandbox/harness/tc_sandbox.py:57-64`; `src/tracecontract/sandbox/harness/tc_sandbox.py:249`; `src/tracecontract/sandbox/harness/tc_sandbox.py:132`; `src/tracecontract/patches.py:26-30`; `tests/test_sandbox_isolation.py:432`; docs/decision_log.md D36; `paper/sections/method.tex:35`; `paper/sections/limitations.tex:11`; `8c13e0c`
* **Builder note:** The checker confirmed the start-up gap and listed further overstated statements (method.tex, reproducibility.tex, STATUS, the D36 heading). Follow-up (D40-D42): harness 0.3.2 starts sandbox children without PYTHONPATH and restores it after the trusted imports. Under 0.3.1, a wrong candidate shipping an `encodings` package received reward 1.0 in Docker; under 0.3.2 it fails. Two probes were added, every reported result was re-run under 0.3.2 (`pilot-v0.3.2`), and the paper, README, STATUS and D40 describe four defects. Code that a snippet imports still controls what that call reports; this in-call limit is documented.

### `security:SEC-2` (low): Runtime-written /work/sitecustomize.py bypassed the static protected-path filter

* **Finding:** At 6c1af59 /work is owned by the sandbox user and persists across calls in a container. A sitecustomize.py written at runtime therefore ran in every later child, because the filter only screens the patch.
* **Skeptics:** 2 of 2 refuted
* **Disposition:** fixed. Harness 0.3.1 starts children with -s -S -P and runs site.main() only after removing candidate paths, so runtime sitecustomize.py and usercustomize.py files no longer load. A Docker probe plants hooks in /work, /tmp and the user site.
* **Evidence:** `src/tracecontract/sandbox/harness/tc_sandbox.py:58-62`; `tests/fixtures/sandbox_probes/startup_probe.py:7-28`; `tests/test_sandbox_isolation.py:440`; `src/tracecontract/sandbox/harness/tc_runner.py:64-69`; docs/decision_log.md D36
* **Builder note:** Follow-up (D40-D42): with no candidate directory on PYTHONPATH at start-up, a package written to `/work` at runtime no longer loads in later calls. The runtime probe now also plants `/work/encodings`.

### `reproducibility:R1` (medium): Paper said prompts were recorded, but no prompts or generator records were tracked

* **Finding:** At 6c1af59 reproducibility.tex:10 said model-generated artifacts were recorded with their prompts. No prompt templates or generator transcripts were tracked, and all 24 model-generated verifier specs had empty generation fields.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** partly fixed. Workflow scripts with their prompt templates, plus 30 standalone agent prompts with prompt and transcript hashes, were exported to experiments/prompts (8c13e0c, c830977, c37b941). The paper and README now say where the prompts are, and that full transcripts are kept outside the repository and identified by hash.
* **Evidence:** `experiments/prompts/README.md:3-6`; `experiments/prompts/agent_prompts.jsonl`; `paper/sections/reproducibility.tex:10`; `README.md:234-235`; tasks/CS-01/verifiers/full_plain/spec.json (generation block)
* **Remaining:** The verifier specs' generation fields are still unfilled and not linked to the exported prompts. Agent transcripts and the D17 proposals.json are not published, so third parties cannot re-check the generator audits or the CS-01 contract rebuild; the paper now says so.
* **Builder note:** Checker corrections accepted: the README only says where the prompts are; one prompt hash is withheld. Follow-up (D40-D42): the prompt export records each workflow run's start, finish and status and marks the six unused agents; the CS-03/CS-04 reference-check audit records now name their writers' transcript hashes.

### `reproducibility:R2` (medium): Image builds called bare python3 -m pip; README omitted prerequisites

* **Finding:** At 6c1af59 wheel downloads ran python3 -m pip from PATH, which fails inside an activated uv venv that has no pip. The README also omitted uv, TeX with biber, and Docker Hub access.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. Both pip calls now use sys.executable, and the dev extra installs pip. The README now lists uv, git, Docker, Docker Hub and PyPI access, TeX with latexmk and biber, and the pip note.
* **Evidence:** `src/tracecontract/sandbox/docker_runner.py:150`; `src/tracecontract/sandbox/docker_runner.py:448`; `pyproject.toml:18`; `README.md:158-167`; `8c13e0c`; `c830977`
* **Builder note:** Follow-up (D40-D42): the README also names github.com (snapshot rebuilds) and the Python version (audit REPRO-2, REPRO-6).

### `reproducibility:R3` (low): README built only CS-01's snapshot before evaluating four tasks

* **Finding:** At 6c1af59 the README rebuilt only the CS-01 snapshot and preflight did not check snapshots. The README evaluate command graded CS-01, then aborted on the missing CS-02 snapshot.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. The README now rebuilds all four snapshots in a loop. Preflight now fails when a snapshot is missing or does not match its manifest.
* **Evidence:** `README.md:182`; `scripts/preflight_final_run.py:55-61`; `8c13e0c`
* **Builder note:** Follow-up (D40-D42): evaluate now checks every snapshot and frozen verifier before grading anything.

### `reproducibility:R4` (low): evaluate did not verify the base snapshot hash or record it

* **Finding:** At 6c1af59 run_matrix only checked that the snapshot directory existed, so a modified snapshot was graded silently. Run manifests did not record the snapshot hash.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. run_matrix now calls verify_snapshot, which recomputes the file-manifest hash, and stops on a mismatch. It records snapshot_manifest_sha256 per task in the manifest, and preflight runs the same check.
* **Evidence:** `src/tracecontract/evaluate.py:68-77`; `src/tracecontract/tasks.py:76-79`; `scripts/preflight_final_run.py:56-61`; `8c13e0c`

### `reproducibility:R5` (low): Evidence ledger missed sensitivity intervals and caption counts

* **Finding:** At 6c1af59 the ledger lacked the 24 interval endpoints printed in the sensitivity table and the summary caption's task and family counts, although it claims to list every printed number.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. The sensitivity ledger entries now include fa_ci95 and fr_ci95. The new post-hoc table and the exact and macro values also have ledger entries.
* **Evidence:** `paper/make_tables.py:177`; `paper/evidence_ledger.md:81-86`; `paper/make_tables.py:125`; `paper/make_tables.py:5-6`
* **Builder note:** Checker correction accepted: the comparison n column was also missing from the ledger. Follow-up (D40-D42): the ledger records the printed n (and the pair count), task and family counts, harness versions, every verifier-table cell and the exact command; stale tables are deleted on regeneration; the 'every number' wording is narrowed in the README, paper/README.md and the ethics section.

### `reproducibility:R6` (low): analysis.json did not record the inputs it was computed from

* **Finding:** At 6c1af59 analysis meta held no revision and no hashes of the labels, mappings and checks read from tasks/. Re-analysis after later task changes silently changed the output.
* **Skeptics:** 1 of 2 refuted
* **Disposition:** fixed. analyze now writes meta.inputs: a git revision plus sha256 of results, the manifest, task.json, candidates (which hold labels), contracts (which hold mappings), construction checks and upstream check ids. These cover every file the analysis reads.
* **Evidence:** `src/tracecontract/analysis.py:211`; `src/tracecontract/analysis.py:221-233`; results/runs/pilot-v0.3/analysis.json meta.inputs; `8c13e0c`
* **Remaining:** The committed pilot-v0.3 analysis.json names 6c1af59 although it was produced by code committed later in 8c13e0c (superseded run; not regenerated).
* **Builder note:** Follow-up (D40-D42): analysis.json records `+dirty` and hashes of the analysis code; the final analysis was regenerated on a committed tree.

### `reproducibility:R7` (low): Grader stdout and stderr were discarded; only an unverifiable hash was kept

* **Finding:** At 6c1af59 verify_candidate kept only log_sha256 of the grader output and wrote no logs, so the 240 pilot-v0.3 hashes could not be checked against anything.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** partly fixed. verify_candidate now writes one log per pair when given log_dir, and evaluate passes results/runs/<id>/logs. That directory is gitignored, so the logs stay local.
* **Evidence:** `src/tracecontract/sandbox/docker_runner.py:420-424`; `src/tracecontract/evaluate.py:102`; `.gitignore:16`; `src/tracecontract/sandbox/harness/tc_runner.py:160-161`
* **Remaining:** `tracecontract grade` keeps no log, and the B1 log hashes of pilot-v0.3 and pilot-v0.3.1 cover empty logs.
* **Builder note:** Follow-up (D40-D42): harness 0.3.2 keeps the repository-test output tails in the host logs; the README says the logs are local only (git-ignored).

### `reproducibility:R8` (low): Documented make -C paper build fails because no Makefile exists

* **Finding:** At 6c1af59 paper/README.md offered 'make -C paper', but paper/ had no Makefile, so the command failed.
* **Skeptics:** 0 of 2 refuted
* **Disposition:** fixed. The make alternative was removed. The README now says to build from paper/ with latexmk (biber needed), after regenerating the tables.
* **Evidence:** `paper/README.md:3-4`; `c830977`

### `reproducibility:R9` (low): Harbor validation listed as tested could not be reproduced from the repository

* **Finding:** At 6c1af59 STATUS listed the Harbor export as validated, but there was no command, script, test or committed fixture to re-run it.
* **Skeptics:** 1 of 2 finished, not refuted (second not finished)
* **Disposition:** fixed. 8c13e0c added scripts/harbor_validate.sh and the FX-01 fixture task. The README gives the command and the Harbor 0.25.0 prerequisite, and D39 records a re-validation under harness 0.3.1.
* **Evidence:** `scripts/harbor_validate.sh:11-20`; `src/tracecontract/harbor_export.py:158`; `.gitignore:17`; `README.md:223-226`; `STATUS.md:81-82`; docs/decision_log.md D39
* **Builder note:** Follow-up (D40-D42): only the top-level `snapshots/` is ignored, the fixture snapshot is tracked, an offline test covers `export_task`, and `scripts/harbor_validate.sh` records its outputs in `results/harbor_validation/`.

### `reproducibility:R10` (low): Annotation guide run step needs a state directory no command created

* **Finding:** At 6c1af59 the guide told annotators to run sandbox-python on a candidate state directory that no command created. Applying the raw patch by hand also gave a different tree from the graded one.
* **Skeptics:** not verified (skeptic stage stopped)
* **Disposition:** fixed. 8c13e0c added 'tracecontract materialize', built on prepare_workspace, so protected test paths are removed as in grading. The README shows the command.
* **Evidence:** `src/tracecontract/cli.py:312-332`; `src/tracecontract/cli.py:444-445`; `README.md:218-220`; `docs/annotation_guide.md:55-61`
* **Builder note:** Follow-up (D40-D42): the annotation guide now shows `snapshot`, `materialize` and `sandbox-python`.

## Final claims audit

Verified: the verifier agent's verdict (yes = the finding is real). Disposition: what the builder did.

| ID | Lens | Severity | Where | Finding | Verified | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| `N1` | numbers | medium | `paper/sections/method.tex:51` | The decision log records two stalled B1 gradings, not one. | yes | fixed: method section gives both stalls and the construction-time truncation |
| `N2` | numbers | medium | `paper/sections/results.tex:8` | This gives the wrong protocol version and timing for one exploratory analysis. | yes | fixed: results section dates each exploratory analysis (v0.3, v0.4, v0.5) |
| `N3` | numbers | medium | `paper/evidence_ledger.md:55` | The ledger claims to list every number in the generated tables. | yes | fixed: ledger records the printed n and the pair count |
| `N4` | numbers | low | `paper/sections/abstract.tex:6` | '6 of 17' is the plain initial-only verifier (C1) only. | yes | fixed: abstract gives 6 of 17 (5 with the audit) |
| `N5` | numbers | low | `paper/sections/introduction.tex:24` | The defect count does not match the rest of the paper. | yes | fixed: introduction counts all defects |
| `N6` | numbers | low | `docs/ownership_and_defense.md:49` | Stale counts. | yes | fixed: AI-work list updated |
| `N7` | numbers | low | `paper/sections/analysis.tex:11` | This line and data.tex:30 list four more-itertools correction requirements. | yes | fixed: data and analysis sections add the unchanged default output (inferred) |
| `N8` | numbers | low | `paper/sections/results.tex:39` | The text names five excluded near misses but the list that follows has three items. | yes | fixed: all five ambiguous near misses listed, with which ones C3/C4 accept |
| `N9` | numbers | low | `paper/sections/analysis.tex:31` | B1 accepts 5 of 17 invalid candidates, but this list covers only four. | yes | fixed: list adds all-uppercase input in inflection |
| `N10` | numbers | low | `paper/sections/results.tex:66` | The cited source does not exist. | yes | fixed: cites the corrections field and D42 |
| `N11` | numbers | low | `paper/sections/ethics.tex:22` | Not every number in the text has the source this sentence (and paper/README.md:8, 'Numbers in results sections come only from generated/*.tex') claims. | yes | fixed: verifier table added to the paper; ethics and paper/README wording narrowed |
| `N12` | numbers | low | `STATUS.md:34` | The sentence covers four protocol versions but cites only three log entries. | yes | fixed: STATUS cites D15, D22, D32, D39, D40 |
| `N13` | numbers | low | `docs/decision_log.md:623` | The stated time range ends too early. | yes | fixed: D41 corrects the time range |
| `PD-01` | procedure | high | `paper/sections/protocol.tex:19` | The workspaces were not isolated, so the 'no access' claims are false. | yes | fixed: protocol section, limitations, data card, data section and D41 describe the real separation |
| `PD-02` | procedure | medium | `README.md:30` | This is false for the pre-correction state, which is part of the pool. | yes | fixed: README, data card, STATUS and paper name the pre-correction-state and B1 exceptions |
| `PD-03` | procedure | medium | `docs/decision_log.md:569` | Git history contradicts this. | yes | fixed: D41 gives the reference-check timing; protocol and limitations corrected |
| `PD-04` | procedure | medium | `paper/sections/limitations.tex:8` | The list leaves out the labeling standard itself. | yes | fixed: limitations, README, data card, data section, ethics and ownership notes name the scenario authorship |
| `PD-05` | procedure | medium | `paper/sections/protocol.tex:48` | This is the paper's only list of deviations, and it leaves out the generation-procedure deviations in D24 and D17. | yes | fixed: protocol section lists the D17/D24 deviations; method section qualifies 'same template' |
| `PD-06` | procedure | medium | `paper/sections/introduction.tex:24` | This is out of date and leaves out the most serious defect. | yes | fixed: introduction rewritten |
| `PD-07` | procedure | medium | `docs/decision_log.md:612` | In all four provenance records the main trace_sha256 field still holds the old sanitize:v1 hash, which matches no transcript in the working tree. | yes | fixed: provenance trace hashes name the published transcripts; manifests rebuilt |
| `PD-08` | procedure | medium | `paper/sections/method.tex:33` | Coming right after 'frozen by content hash', this implies the check-list hash was part of the freeze record. | yes | fixed: method section says the check-list hash was added after pilot-v0.3 |
| `PD-09` | procedure | medium | `docs/data_card.md:32` | The data card describes the held-out pool without any of the exceptions D37 discloses. | yes | fixed: data card lists the exceptions |
| `PD-10` | procedure | medium | `README.md:253` | The bullet lists three departures, but D37 lists six. | yes | fixed: README, paper and protocol v0.5 list every departure |
| `PD-11` | procedure | low | `paper/sections/method.tex:51` | There were two stalled gradings, not one. | yes | fixed: see N1; the minor D28 defect is named |
| `PD-12` | procedure | low | `docs/decision_log.md:452` | Three problems. | yes | fixed: D41 records the prompt differences and the six stopped agents; paper says registered generators were audited |
| `PD-13` | procedure | low | `docs/decision_log.md:474` | Mapper 2 did not get the same instructions as mapper 1 for CS-01, CS-03 and CS-04. | yes | fixed: D41 and the paper note the extra mapper instruction |
| `PD-14` | procedure | low | `docs/ownership_and_defense.md:49` | The record of AI-produced work is out of date. | yes | fixed: ownership notes and STATUS updated |
| `PD-15` | procedure | low | `docs/submission_readiness.md:106` | Ticking this box as 'completed' contradicts STATUS.md:52-53, which says the skeptic stage was stopped before every finding was checked. | yes | fixed: checklist item unticked and reworded |
| `PD-16` | procedure | low | `docs/submission_readiness.md:97` | The draft AI-use disclosure states, outside the 'to be completed truthfully' bracket, that the human authors 'performed the human annotation'. | yes | fixed: disclosure draft rewritten |
| `PD-17` | procedure | low | `docs/decision_log.md:553` | The cross-reference points nowhere. | yes | fixed: D42 records the B1 probe; D41 fixes the pointer |
| `PD-18` | procedure | low | `paper/sections/results.tex:66` | The decision log has no CS-01 mapping note. | yes | fixed: see N10 |
| `PD-19` | procedure | low | `experiments/prompts/workflows/tracecontract-heldout__wf_5ef9efad-a4c.js:1` | Every exported header labels the run record's 'timestamp' as 'started', but that field holds the finish time. | yes | fixed: export headers give start, finish and status; prompts re-exported |
| `PD-20` | procedure | low | `STATUS.md:83` | The repository holds no record of the Harbor validations: no lint log, no trial result.json and no tc_detail.json. | no | not a defect (verifier); outputs are now recorded in results/harbor_validation/ anyway |
| `PD-21` | procedure | low | `STATUS.md:127` | This list of material still in git history, which the owner needs to decide whether to rewrite history, is incomplete. | yes | fixed: STATUS lists it; data card says the working tree is redacted |
| `F01` | consistency | medium | `paper/sections/introduction.tex:24` | The contribution list names only the two resource defects. | yes | fixed: see PD-06 |
| `F02` | consistency | medium | `experiments/protocol.md:81` | Calls the intended requirements 'pre-registered' and calls the reference contract 'ground truth', although a model operationalised it and only a model has reviewed it. | yes | fixed: protocol v0.5 §13, D41, table caption and the task builder's label |
| `F03` | consistency | medium | `paper/evidence_ledger.md:55` | The ledger says it lists every number in the generated tables. | yes | fixed: see N3 and N11 |
| `F04` | consistency | medium | `docs/research_brief.md:17` | Stale. | yes | fixed: brief cites D34 |
| `F05` | consistency | medium | `paper/sections/related.tex:8` | This negative claim covers VibeSWEBench. | yes | fixed: related work hedges the negative claim and names the unread revision |
| `F06` | consistency | low | `paper/sections/results.tex:8` | This is wrong for the construction-intent sensitivity analysis (Table sensitivity, marked exploratory). | yes | fixed: see N2 |
| `F07` | consistency | low | `paper/sections/results.tex:66` | The cited source does not exist: the decision log has no CS-01 mapping note. | yes | fixed: see N10 |
| `F08` | consistency | low | `docs/decision_log.md:468` | The construction check records 98 ASCII differences for CS-03 alternative 1 (apostrophe-joined tokens), so only the pre-correction state matches on all ASCII probes. | yes | fixed: D41 corrects D33; analysis section corrected |
| `F09` | consistency | low | `paper/sections/method.tex:51` | The decision log records two stalls: CS-04 alt-1 in pilot-v0.2 (D28) and CS-04 nm-1 in pilot-v0.2-h2 (D30). | yes | fixed: see N1 |
| `F10` | consistency | low | `docs/ownership_and_defense.md:49` | Stale. | yes | fixed: see N6; D25 advice corrected |
| `F11` | consistency | low | `docs/submission_readiness.md:96` | The draft disclosure states, outside the bracket, that the human authors 'performed the human annotation'. | yes | fixed: see PD-16 |
| `F12` | consistency | low | `STATUS.md:27` | Gives a clean held-out record and never mentions the D37 departures. | yes | fixed: STATUS and data card carry the caveats |
| `F13` | consistency | low | `paper/sections/protocol.tex:19` | The pool listed just above includes the pre-correction state. | yes | fixed: see PD-02 |
| `F14` | consistency | low | `paper/sections/protocol.tex:48` | Reads as four accepted tasks. | yes | fixed: yield wording says none is accepted yet |
| `F15` | consistency | low | `README.md:151` | In this project 'natural' means real-user sessions (README.md:17, data.tex:5). | no | not a defect (verifier: defined vocabulary); the generated text now says 'observed pre-correction state' |
| `F16` | consistency | low | `README.md:113` | States a model-proposed label as fact; the independent check disputes the inflection label. | yes | fixed: README qualifies the label and the generalisations |
| `F17` | consistency | low | `docs/research_brief.md:672` | Stale status line. | yes | fixed: brief status line cites D35, D39 and D40 |
| `F18` | consistency | low | `docs/research_brief.md:507` | Calls the planned human labels 'ground truth'. | no | not a defect (verifier); no change |
| `F19` | consistency | low | `STATUS.md:52` | Never says that the reviewers and 'independent skeptics' were model agents, so it can read as human review. | yes | fixed: README and STATUS say the reviews were run by model agents |
| `F20` | consistency | low | `paper/references.bib:8` | Three cited entries cannot be checked against the verified bibliography, even though its scope line says it covers paper/references.bib. | no | not a defect (verifier: disclosed in the file); no change |
| `F21` | consistency | low | `docs/decision_log.md:6` | This is the log's only date heading. | yes | fixed: date heading inserted (the one non-append edit, recorded in D41) |
| `F22` | consistency | low | `paper/sections/analysis.tex:9` | The cited essay predicts only that a task may reward the rejected behaviour. | yes | fixed: analysis section separates what the essay predicts |
| `F23` | consistency | low | `paper/sections/results.tex:7` | The text says this convention applies throughout, but the sensitivity and paired-comparison tables print zero-width intervals ([0.00, 0.00], [+0.00, +0.00]) without the marker. | yes | fixed: degenerate intervals marked in every table |
| `F24` | consistency | low | `docs/data_card.md:40` | The reference is not written by the study. | yes | fixed: data card describes the reference as the agent's final state |
| `F25` | consistency | low | `paper/sections/abstract.tex:6` | 6 of 17 is the plain initial-only condition (C1) only. | yes | fixed: see N4 |
| `REPRO-1` | reproducibility | high | `README.md:227` | The documented Harbor re-check cannot run from a clone. | yes | fixed: fixture snapshot tracked; export tested offline and checked from a fresh clone |
| `REPRO-2` | reproducibility | medium | `README.md:162` | The network list leaves out GitHub. | yes | fixed: README names github.com |
| `REPRO-3` | reproducibility | medium | `paper/evidence_ledger.md:55` | The ledger does not hold the n values printed in Table tab:comparisons. | yes | fixed: see N3; harness versions and the exact command recorded; stale tables deleted |
| `REPRO-4` | reproducibility | medium | `README.md:237` | Grading is not bit-reproducible, and neither is analysis.json. | yes | fixed: README and reproducibility section distinguish byte-identical regeneration from outcome agreement |
| `REPRO-5` | reproducibility | low | `THIRD_PARTY_LICENSES/README.md:29` | The table of where upstream code lives understates these four files and misses several others. | yes | fixed: licence path map lists every embedding file |
| `REPRO-6` | reproducibility | low | `README.md:171` | The requirements say Python ≥ 3.12 (line 160), but this command needs 3.13. | yes | fixed: README states the tested Python version |
| `REPRO-7` | reproducibility | low | `experiments/prompts/README.md:3` | Five of the 14 exported scripts are not exact: redaction changed them, and their headers show either a different original hash or `withheld`. | yes | fixed: export README template rewritten |
| `REPRO-8` | reproducibility | low | `results/runs/pilot-v0.3.1/analysis.json:1709` | The analysis records revision c37b941, but it read uncommitted inputs. | yes | fixed: analysis records +dirty and code hashes; regenerated on a committed tree |
| `REPRO-9` | reproducibility | low | `docs/annotation_guide.md:60` | The guide tells reviewers to run a candidate but never says how to get its <state-dir>. | yes | fixed: annotation guide shows snapshot, materialize and sandbox-python |
| `REPRO-10` | reproducibility | low | `paper/README.md:8` | This rule does not match the folder. | yes | fixed: see N11 |

### Completeness critic

Areas the critic found that no lens had checked, its findings, and what the builder did.

1. **Annotation guide as a blind labeling procedure (can a human follow it as written?).** `docs/annotation_guide.md:104`: The guide sends reviewers to files that show the answers before they judge.
   **Disposition:** fixed: blinded review packet (`tracecontract review-packet`, `merge-reviews`) and annotation guide v0.3 (D43)
2. **Model identity and per-artifact generation provenance.** `paper/sections/data.tex:18`: No public document names the model or its version.
   **Disposition:** disclosed: the paper and data card say the session model is recorded in the published transcripts and that the other agents' model identifiers are not in the repository (D43)
3. **Run outputs other than analysis.md: the HTML report text and the superseded run folders.** `results/runs/pilot-v0.3.1/report.html:26`: experiments/protocol.md:222-223 (v0.4 §12) says: 'Macro rates and per-metric denominators, which §6 already required, are now shown in every output.' The report README calls 'The report' does not meet this.; `results/runs/pilot-v0.2/analysis.md:3`: protocol.md:155-157 says pilot-v0.2 and pilot-v0.2-h2 are superseded and 'not reported as pilot results'.; `results/runs/pilot-v0.3.1/report.html:8733`: The report is one self-contained file.
   **Disposition:** fixed: run index and superseded-run notes; D40 records the older reports' gaps; the HTML report embeds the licence notices
4. **Public text written after the audited commit 787176e (29a1382, 0a94529 and the working tree).** `experiments/protocol.md:264`: D41 (docs/decision_log.md:740) and paper protocol.tex:48 say that mapper 2 for all tasks and mapper 1 for CS-02 got the extra sentence.
   **Disposition:** fixed: D41 corrects the protocol v0.5 wording; the text written after 787176e went to the verification step below
5. **Implementation and isolation claims compared with the source code.** No problem found.
   **Disposition:** no problem found
6. **Related-work claims checked against the primary papers (not only the brief).** No problem found.
   **Disposition:** no problem found
