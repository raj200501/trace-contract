export const meta = {
  name: 'natural-phase',
  description: 'Natural arm (D64, D65): one phase of one accepted family: preparation, generators, registration, with host coordinators running the CLI steps',
  phases: [
    { title: 'Prep', detail: 'workspaces and prompts (host)' },
    { title: 'Generate', detail: 'generator agents with verbatim, hash-checked prompts' },
    { title: 'Register', detail: 'records, contracts, verifiers, candidates, freezes (host)' },
  ],
}
// The natural arm's per-phase workflow (decision log D64, D65): one phase (args.phase, P1 to P7) of one accepted family
// (args.task). A host coordinator prepares the phase's workspaces and prompts, the generators run with their rendered
// prompts verbatim (sent only when the script's own sha256 of the text equals the renderer's), and coordinators register
// the runs; the loops of P3 and P5 run inside their phase. The builder commits scripts/record_phase_end.py's line after
// each phase, before the family's next phase. Launch with the Workflow tool: args {task, phase, transcripts,
// config_b_model}. Not yet run: the build stopped at a usage limit before the first natural agent (D66).
// SHA-256 of a string's UTF-8 bytes, in plain JavaScript (no Node or Web APIs), for the workflow scripts.
const SHA_K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]
const utf8Bytes = (s) => {
  const out = []
  for (let i = 0; i < s.length; i++) {
    let c = s.charCodeAt(i)
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
      const d = s.charCodeAt(i + 1)
      if (d >= 0xdc00 && d <= 0xdfff) { c = 0x10000 + ((c - 0xd800) << 10) + (d - 0xdc00); i++ }
    }
    if (c < 0x80) out.push(c)
    else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63))
    else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63))
    else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63))
  }
  return out
}
const rotr = (x, n) => (x >>> n) | (x << (32 - n))
const sha256hex = (s) => {
  const b = utf8Bytes(s)
  const n = b.length
  b.push(0x80)
  while (b.length % 64 !== 56) b.push(0)
  const hi = Math.floor(n / 0x20000000), lo = (n * 8) >>> 0
  b.push((hi >>> 24) & 255, (hi >>> 16) & 255, (hi >>> 8) & 255, hi & 255, (lo >>> 24) & 255, (lo >>> 16) & 255, (lo >>> 8) & 255, lo & 255)
  const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
  const W = new Array(64)
  for (let i = 0; i < b.length; i += 64) {
    for (let t = 0; t < 16; t++) W[t] = ((b[i + 4 * t] << 24) | (b[i + 4 * t + 1] << 16) | (b[i + 4 * t + 2] << 8) | b[i + 4 * t + 3]) >>> 0
    for (let t = 16; t < 64; t++) {
      const s0 = rotr(W[t - 15], 7) ^ rotr(W[t - 15], 18) ^ (W[t - 15] >>> 3)
      const s1 = rotr(W[t - 2], 17) ^ rotr(W[t - 2], 19) ^ (W[t - 2] >>> 10)
      W[t] = (W[t - 16] + s0 + W[t - 7] + s1) >>> 0
    }
    let [a, bb, c, d, e, f, g, h] = H
    for (let t = 0; t < 64; t++) {
      const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + SHA_K[t] + W[t]) >>> 0
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & bb) ^ (a & c) ^ (bb & c))) >>> 0
      h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = bb; bb = a; a = (t1 + t2) >>> 0
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + bb) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0
  }
  return H.map(x => x.toString(16).padStart(8, '0')).join('')
}
const PHASES = ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7']
const T = args && args.task, PH = args && args.phase
if (!/^NP-[0-9]{2}$/.test(T || '') || !PHASES.includes(PH)) throw new Error('args: {task: "NP-xx", phase: "P1".."P7"}')
const R = '/home/user/trace-contract'
const TD = `${R}/data/natural/tasks/${T}`
const WS = `/home/user/nat_ws/${T}`
const RR = `/home/user/nat_runrec/${T}`
const LOG = `${RR}/host_log.jsonl`
// Given at launch, so that no session-local path or model option is in the repository (D65): the build session's
// directory of workflow-agent transcripts, and the agent tool's model option for configuration B.
const SUB = args && args.transcripts
const CONFIG_B_MODEL = args && args.config_b_model
if (!SUB || !CONFIG_B_MODEL) throw new Error('args.transcripts and args.config_b_model are required')
const GEN_WF = `${R}/experiments/prompts/workflows/tracecontract-generate__wf_b796bb4f-1dd.js`
const HELD_WF = `${R}/experiments/prompts/workflows/tracecontract-heldout__wf_b428f318-391.js`

const HOST = `You are a host coordinator of the build session for natural family ${T}, phase ${PH} (decision log D64 and D65). You run only deterministic host steps of the natural-arm recipe, with the repository's CLI and scripts.
Context: the study's owner asked the build session to keep building the study and to see it through without asking further questions. Their standing constraints: no spending beyond this session; no network use beyond what the recipe's own tools do; no thread text, login, handle, e-mail address or natural repository name in any file of the repository outside the git-ignored data/natural/; no model identifier anywhere in the repository; no commit or push by you.
Rules (D65, "Host coordinators"):
- Write no generated content yourself (no requirement, test, contract, state or candidate); never repair, complete or edit a generator's output; give a generator nothing its template does not name. If a step cannot be done as the recipe says, set stop = true and say why instead of improvising.
- Before your first command read docs/decision_log.md D64 and D65 in full, ${RR}/state.md (what earlier steps did), experiments/prompts/natural/README.md and the header of every template you render. The registration commands and their flags are the source workflows' (${GEN_WF}, ${HELD_WF}), with the host's changes D64 lists: a --generation-record for every contract, verifier and constructed candidate, and generator labels with claude-code-subagent replaced by config-A (config-B for the labeler and its revision).
- Paths: repository ${R}; task directory ${TD} (git-ignored); snapshot root ${R}/data/natural/snapshots; workspaces ${WS}/<name>; private run records ${RR}/ (prompts in prompts/, generation records in records/, grades in grades/, your helper scripts in host_scripts/). Python: ${R}/.venv/bin/python -B, with PYTHONDONTWRITEBYTECODE=1; CLI: ${R}/.venv/bin/tracecontract.
- Read only this family's task directory, workspaces and run records, and the repository's code, docs and manifests. Do not list, read or search another family's task directory, workspaces or run records, or /home/user/nat_runrec/_aborted. Write only under ${RR}, ${WS} and ${TD}: never under data/manifests/ (run natural-index, if at all, with --out under ${RR}), never into tracked files of the repository, never into the build session's scratch directories.
- Log every command to ${LOG} as it runs (time, command, exit code, short output), through a wrapper script in ${RR}/host_scripts/; an entry added afterwards is marked retroactive, with its reason. No thread text in the log.
- Workspaces only with scripts/make_agent_workspace.py. Prompts only with scripts/check_natural_prompts.py render: save each with --out to ${RR}/prompts/<workspace>.txt, check it with render --verify, and return it verbatim, copied from that file, with the prompt_sha256 the renderer printed. Pass a value that comes from a file or from an agent's run with --set-file. Values taken from an agent's run (a review's issues, an attack's target and description, a near miss's description, a mapping file) are read from its transcript or workspace by a script, never retyped.
- A run's transcript is the agent-*.jsonl under ${SUB}/<workflow run id>/ whose .meta.json description equals the run's label. Generation records only with scripts/agent_run_record.py from that transcript, after checking the transcript's first message with check_natural_prompts.py render --verify (or --record).
- Grade only with tracecontract grade (single grades where D64 says so); Docker runs only through the CLI and the workspace wrappers. Never commit or push.
- Never use the task-list tools (TaskCreate, TaskUpdate, TaskList, TaskGet): the shared list's titles are visible to the natural agents that run beside you (D65). Keep your own notes in ${RR}/state.md.
- Economy (the owner's usage budget, D68): keep your context small. Send long command output (JSON reports, grades, logs) to files in ${RR} and print only short summaries; do not re-read a file you have read; combine the commands of a sub-step in one logged helper script where that is clear; check what the recipe needs, not more.
- Re-run rule (D64): a generator run that registers nothing (no proposals, no test file, an unchanged state) is re-run once, in a new workspace named <workspace>-r2, with the same template and values except WS; return it in reruns. Nothing is regenerated because of a check or grade outcome.`

const PROMPTS = { type: 'array', items: { type: 'object', properties: { role: { type: 'string' }, label: { type: 'string' }, prompt: { type: 'string' }, prompt_sha256: { type: 'string' }, config: { type: 'string', enum: ['A', 'B'] } }, required: ['role', 'label', 'prompt', 'prompt_sha256', 'config'] } }
const HOSTOUT = { type: 'object', properties: { done: { type: 'string' }, next_prompts: PROMPTS, reruns: PROMPTS, state: { type: 'string' }, problems: { type: 'array', items: { type: 'string' } }, stop: { type: 'boolean' } }, required: ['done', 'next_prompts', 'reruns', 'state', 'problems', 'stop'] }
// The review schema of the held-out workflow wf_b428f318-391, verbatim (D65, "Agent options").
const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['ok', 'needs_fix'] },
    issues: { type: 'array', items: { type: 'object', properties: {
      test: { type: 'string' },
      kind: { type: 'string', enum: ['over_specified', 'unspecified_behavior', 'wrong_expectation', 'flaky_risk', 'missing_coverage'] },
      requirement_ids: { type: 'array', items: { type: 'string' } },
      explanation: { type: 'string' },
      suggested_fix: { type: 'string' } },
      required: ['test', 'kind', 'requirement_ids', 'explanation', 'suggested_fix'] } },
    coverage: { type: 'string', description: 'tests per requirement id' },
    validation: { type: 'string', description: 'outcomes of grading the reference and the dev no-op' },
  },
  required: ['verdict', 'issues', 'coverage', 'validation'],
}

// Agent options by role, as the source workflows set them (D65): generate-workflow roles run as the default workflow
// agent; held-out-workflow roles as general-purpose (reviewers with the review schema); the labeler roles in configuration B.
const R2 = '(-r2)?'
const ROLE_RULES = [
  [new RegExp(`^(contract-initial|contract-full|testgen-initial|testgen-full|freeform|diff-derived|attack-initial|attack-full|alt-initial|alt-full|revise-(initial|full)-[1-3]|refcontract)${R2}$`), 'A', {}],
  [new RegExp(`^(refcheck|refcheck-fix-[12]|eval-alt-[12]|eval-nm-[123]|mapper-[12])${R2}$`), 'A', { agentType: 'general-purpose' }],
  [new RegExp(`^refcheck-review-[123]${R2}$`), 'A', { agentType: 'general-purpose', schema: REVIEW_SCHEMA }],
  [new RegExp(`^(labeler|labeler-revision)${R2}$`), 'B', { model: CONFIG_B_MODEL }],
]
const roleRule = (role) => ROLE_RULES.find(([re]) => re.test(role || ''))
const problemOf = (p) => {
  if (!p) return 'missing prompt'
  const rule = roleRule(p.role)
  if (!rule) return `unknown role ${JSON.stringify(p.role)}`
  if (p.config !== rule[1]) return `${p.role} is configuration ${rule[1]}, not ${p.config}`
  if (p.label !== `${T}:${p.role}`) return `${p.role}: the label must be ${T}:${p.role}`
  if (typeof p.prompt !== 'string' || !/^[0-9a-f]{64}$/.test(p.prompt_sha256 || '')) return `${p.role}: no prompt or no sha256`
  const got = sha256hex(p.prompt)
  if (got !== p.prompt_sha256) return `${p.role}: the returned text hashes to ${got}, not ${p.prompt_sha256}`
  return null
}

const out = { task: T, phase: PH, steps: [], sent: [], ok: false }
const rec = (name, h) => { out.steps.push({ name, done: h ? String(h.done).slice(0, 2000) : null, problems: h ? h.problems : ['no host result'], stop: h ? h.stop : true }); return h }
const halted = (h) => !h || h.stop
const finish = (ok) => { out.ok = !!ok; return out }
const host = (step, text, ph) => agent(`${HOST}\n\nStep ${PH}/${step}.\n${text}\n\nWhen the step is done, append a short section "## ${PH} ${step}" to ${RR}/state.md (what was done, ids, outcomes, what the next step needs; no thread text). Return: what you did (done); the prompts of the next generators (next_prompts: role = workspace or group name, label = '${T}:' + role, config A or B as D64 gives, prompt verbatim and its sha256); any re-runs under D64's re-run rule (reruns, same form); a short state summary for the next step; problems; and stop = true only if the family cannot continue under the recipe.`, { label: `${T}:host:${PH}:${step}`, phase: ph || 'Register', schema: HOSTOUT, effort: 'high' })

// Prompts are sent only when the workflow's own sha256 of the text equals the renderer's (D65); one resend, then stop.
const verified = async (step, prompts) => {
  if (!prompts || !prompts.length) return []
  let bad = prompts.map(p => [p, problemOf(p)]).filter(([, e]) => e)
  if (!bad.length) return prompts
  log(`${T} ${PH}/${step}: ${bad.length} prompt(s) failed the check; asking once more`)
  const again = rec(`${step}-resend`, await host(`${step}-resend`, `The workflow refused these prompts: ${JSON.stringify(bad.map(([p, e]) => ({ role: p && p.role, problem: e })))}. Re-read each from its saved file in ${RR}/prompts/ (do not render again unless a value was wrong), check it with render --verify, and return in next_prompts only these prompts, verbatim, with the right role, label, configuration and sha256.`, 'Prep'))
  if (halted(again)) return null
  const fixed = again.next_prompts || []
  const still = fixed.map(p => [p, problemOf(p)]).filter(([, e]) => e)
  if (still.length || fixed.length !== bad.length) { log(`${T} ${PH}/${step}: prompts still refused: ${JSON.stringify(still.map(([p, e]) => e))}`); out.steps.push({ name: `${step}-refused`, problems: still.map(([, e]) => e), stop: true }); return null }
  const keep = prompts.filter(p => !problemOf(p))
  return keep.concat(fixed)
}
const gen = async (p) => {
  const [, , opts] = roleRule(p.role)
  out.sent.push({ role: p.role, label: p.label, prompt_sha256: p.prompt_sha256 })
  const r = await agent(p.prompt, { label: p.label, phase: 'Generate', ...opts })
  return { role: p.role, label: p.label, out: r == null ? null : (typeof r === 'string' ? r.slice(0, 4000) : r) }
}
const runAll = async (ps) => ps && ps.length ? (await parallel(ps.map(p => () => gen(p)))).filter(Boolean) : []
// Register the runs of a step; run its re-runs once and register them.
const register = async (step, outs, text) => {
  let h = rec(step, await host(step, `${text}\nRuns of this step (role, label, final answer cut to 4000 characters, or structured output): ${JSON.stringify(outs)}`))
  if (!halted(h) && h.reruns && h.reruns.length) {
    const re = await verified(`${step}-reruns`, h.reruns)
    if (!re) return null
    const reOuts = await runAll(re)
    const h2 = rec(`${step}-reruns`, await host(`${step}-reruns`, `${text}\nThis registers the re-runs only (D64's re-run rule): ${JSON.stringify(reOuts)}. Earlier state: ${h.state}. Do not re-run again; a re-run that registers nothing is recorded as such. Then finish the rest of the step as its text says.`))
    if (!h2) return null
    h = { ...h2, next_prompts: (h.next_prompts || []).concat(h2.next_prompts || []) }
  }
  return h
}
// One preparation step, its generators and their registration.
const simplePhase = async (prepText, regText) => {
  phase('Prep')
  const prep = rec('prep', await host('prep', prepText, 'Prep'))
  if (halted(prep)) return null
  const ps = await verified('prep', prep.next_prompts)
  if (!ps || !ps.length) { out.steps.push({ name: 'prep-empty', problems: ['no prompt to send'], stop: true }); return null }
  phase('Generate')
  const outs = await runAll(ps)
  phase('Register')
  return register('register', outs, regText)
}

if (PH === 'P1') {
  const h = await simplePhase(
    `P1. The proposer workspaces ${WS}/contract-initial and ${WS}/contract-full and their prompts ${RR}/prompts/contract-initial.txt and contract-full.txt were made before D65. Check that D65 is in the committed decision log (git show HEAD:docs/decision_log.md), that each saved prompt renders equal (check_natural_prompts.py render experiments/prompts/natural/contract_v1-natural.txt --variant initial_only or full_session --set TASK=${T} --set WS=<workspace> --set SESSION_ID=<the session id of session.json> --verify <file>) and has the sha256 D65 logs for ${T}, and that both workspaces still hold only manifest.json, an empty scratch/, the session file and session_events.json. Return the two prompts as next_prompts (roles contract-initial and contract-full, config A), copied from the saved files.`,
    `P1 registration. For each proposer: verify its prompt in its transcript, make its generation record (--config config-A), and run make-contract ${TD} --variant initial_only (contract-initial) or full_session (contract-full) --proposals <workspace>/proposals.json --proposer model:config-A:contract:v1 --generation-record <record>. Do not repair rejected proposals. Report make-contract's verdict, the acceptance gate's reasons (non_user_evidence included) and the contract's requirement counts. A proposer that wrote no proposals.json registered nothing (re-run rule). Return no next_prompts.`)
  return finish(!halted(h))
}

if (PH === 'P2') {
  const h = await simplePhase(
    `P2 preparation. Build the eight P2 workspaces of the D64 table with scripts/make_agent_workspace.py, with the task image and the pytest arguments the recipe gives: testgen-initial, testgen-full, freeform, diff-derived, the attack groups attack-initial and attack-full (--root ${WS}/attack-<initial|full> --name a1 to a4, as the attack template's header says) and alt-initial and alt-full. Check that every reference.diff in them has the sha256 D65 logs for ${T}, and stop if one does not. Render their eight prompts: testgen:v1-natural with variant initial_plain (testgen-initial), full_plain (testgen-full) and llm_freeform (freeform); b3:v1 (diff-derived); attack:v1-natural initial_only and full_session; alt:v1-natural initial_only and full_session; with the values the templates name. Return the eight prompts (role = the workspace, or the attack group's name).`,
    `P2 registration. C1 (initial_plain, from testgen-initial), C3 (full_plain, from testgen-full) and B2 (llm_freeform, from freeform): copy each workspace's tests into the task's verifiers/<id>/tests, build-verifier with the condition and contract id of the source workflow's gens entries and its generation record, and freeze all three at once (F4). B3 (diff-derived): build diff_derived from its tests with its generation record, not frozen (P3 selects its tests). The four development attacks of each variant: add-candidate <task>-dev-attack-<variant>-a<k> --origin dev_attack --split dev --state-dir ${WS}/attack-<initial|full>/a<k>/repo, with the target requirement id and the one-line description the agent returned (read from its transcript by a script), as the attack template's header says, with the agent's generation record. The two development alternatives: add-candidate <task>-dev-alt-<variant> --origin valid_alternative --split dev, as the alt template's header says. Return no next_prompts.`)
  return finish(!halted(h))
}

if (PH === 'P3') {
  phase('Prep')
  const prep = rec('prep', await host('prep', `P3 preparation. (1) C2 and C4: create initial_audited and full_audited as copies of initial_plain's and full_plain's tests, build them with the generator's record (the source workflow's AUDIT_RUN steps, run by you), and run audit:v1 once on each (iteration 0), saving the JSON each audit run prints as ${RR}/grades/audit-<verifier id>-0.json. (2) B3: grade diff_derived three single times on the reference and once on the development no-op (records in ${RR}/grades/), run scripts/select_b3_tests.py, then rebuild, confirm and freeze it, or record B3 unavailable as select_b3_tests.py does. (3) For each audited verifier whose audit has findings, build its reviser workspace (role reviser-initial or reviser-full, named revise-initial-1 or revise-full-1, --tests-from the verifier's tests, --dev-candidates its variant's development candidates) and render its revise:v1-natural prompt (variant initial_audited or full_audited, ITER=1, FINDINGS from the saved audit JSON by a script, with --set-file). Return the reviser prompts (none if neither audit has findings).`, 'Prep'))
  if (halted(prep)) return finish(false)
  let ps = prep.next_prompts || [], state = prep.state
  for (let i = 1; i <= 3 && ps.length; i++) {
    const v = await verified(`round${i}`, ps)
    if (!v) return finish(false)
    phase('Generate')
    const outs = await runAll(v)
    phase('Register')
    const h = await register(`round${i}`, outs, `P3, revision round ${i}. State: ${state}. For each reviser of this round: verify its prompt and make its generation record; replace the audited verifier's tests with the reviser's tests; combine the run records of the generator and its revisers so far (agent_run_record.py --combine); rebuild the verifier with the combined record; run audit:v1 again (iteration ${i}) and save its printed JSON as ${RR}/grades/audit-<verifier id>-${i}.json. If an audited verifier still has findings and fewer than 3 revisions have run for it, build its next reviser workspace (revise-<initial|full>-${i + 1}) and render its revise prompt (ITER=${i + 1}); return those prompts. A reviser whose tests are unchanged registered nothing (re-run rule, workspace revise-<initial|full>-${i}-r2).`)
    if (halted(h)) return finish(false)
    ps = h.next_prompts || []; state = h.state
  }
  const close = rec('close', await host('close', `P3 closing. State: ${state}. Record each audit with tracecontract audit ... --record N --previous ${RR}/grades/audit-<verifier id>-0.json ... audit-<verifier id>-N.json (all N + 1 iteration records, iteration 0 first; N = its number of revisions; --record 0 also takes --previous with iteration 0), with the same --contract and --audit-set as the loop, and freeze initial_audited and full_audited, also when an audit still fails after 3 revisions (D27). Check that C1, C3, B2 and B3 (or B3 unavailable) are frozen, and run validate-task. Return no next_prompts.`))
  return finish(!halted(close))
}

if (PH === 'P4') {
  const h = await simplePhase(
    `P4 preparation. Check that every verifier of the task is frozen (P3 is closed). Build the refcontract workspace (role refcontract) and render the refcontract:v1 prompt. Return it.`,
    `P4 registration. Verify the drafter's prompt, make its generation record, and run make-contract ${TD} --variant reference --proposals <refcontract workspace>/proposals.json --proposer model:config-A:refcontract:v1 --generation-record <record>. Report the contract's scored active requirements, those introduced at the correction (contract.correction_event_ids), and the acceptance gate's reasons. If the reference contract has no scored active requirement, stop (D64 decision 14). Return no next_prompts.`)
  return finish(!halted(h))
}

if (PH === 'P5') {
  phase('Prep')
  const prep = rec('prep', await host('prep', `P5 preparation. Build the refcheck workspace (role refcheck, with the task image) and the labeler workspace (role labeler, without --image, with the harness documentation the role gives), and render the refcheck:v1-natural prompt (config A) and the labeler:v1-natural prompt (config B). Return both.`, 'Prep'))
  if (halted(prep)) return finish(false)
  const first = await verified('prep', prep.next_prompts)
  if (!first || first.length !== 2) return finish(false)
  phase('Generate')
  const wouts = await runAll(first)
  phase('Register')
  const w = await register('write', wouts, `P5 registration of the two writers. Reference checks: verify the prompt, make the generation record, copy the tests into verifiers/reference_check/tests, build-verifier reference_check --condition reference_check --contract-id ${T}-reference --generation-record <record>, and validate them as D64 says (three single grades on the reference, one on the development no-op; records in ${RR}/grades/). Then build the first review workspace (role refcheck-review, named refcheck-review-1, --tests-from the reference checks) and render the review:v1-natural prompt with VALIDATION from that validation. Labeler (configuration B): verify, make its generation record (--config config-B), copy its tests into verifiers/independent_label/tests, build-verifier independent_label --condition reference_check --contract-id ${T}-reference --sidecar --generation-record <record>, grade it three single times on the reference and three on the development no-op, and decide by D64's rule whether it is usable as written. Usable: freeze it and write verifiers/independent_label/status.json (status usable, round 1, reasons). Not usable, and at least one check can be named: build its revision workspace (role labeler with --tests-from its tests, named labeler-revision) and render the labeler-revise:v1-natural prompt with FAILING (check ids only, one per line, sorted, distinct). Not usable and nothing can be named: freeze it with status unusable, round 1, and the reasons. Return as next_prompts the review prompt and, if any, the labeler revision prompt.`)
  if (halted(w)) return finish(false)
  let pending = w.next_prompts || [], state = w.state, fixes = 0, closed = false
  for (let k = 1; k <= 6 && pending.length; k++) {
    const v = await verified(`round${k}`, pending)
    if (!v) return finish(false)
    phase('Generate')
    const outs = await runAll(v)
    phase('Register')
    const instr = []
    const lab = outs.find(o => /^labeler-revision/.test(o.role))
    const fix = outs.find(o => /^refcheck-fix-/.test(o.role))
    const review = outs.find(o => /^refcheck-review-/.test(o.role))
    if (lab) instr.push(`Labeler revision (${lab.role}): verify it, make its generation record (config-B), combine it with the writer's record (agent_run_record.py --combine), copy its tests into verifiers/independent_label/tests, rebuild the sidecar with the combined record, grade it three and three times again, and freeze independent_label with verifiers/independent_label/status.json (status by D64's rule, round 2, reasons).`)
    if (fix) instr.push(`Fix ${fix.role}: verify it, make its generation record, copy its tests into verifiers/reference_check/tests, rebuild reference_check with the combined record of the writer and its fixers so far, validate it again as before, then build the next review workspace refcheck-review-${fixes + 1} and render its review prompt with the new VALIDATION; return it.`)
    if (review) {
      if (!review.out || typeof review.out !== 'object') { out.steps.push({ name: `round${k}-review`, problems: [`${review.role} returned no review`], stop: true }); return finish(false) }
      const verdict = review.out.verdict
      instr.push(`Review ${review.role}: verify it and make its generation record. Its verdict is ${verdict}.`)
      if (verdict === 'needs_fix' && fixes < 2) {
        fixes += 1
        instr.push(`D33: ${fixes - 1} fix round(s) have run, at most 2, so build the fix workspace (role refcheck-review, named refcheck-fix-${fixes}, --tests-from the reference checks) and render the fix:v1-natural prompt with ISSUES: the review's issues, taken by a script from the StructuredOutput call in the review's transcript and serialised as compact JSON with the review schema's five keys in its order (test, kind, requirement_ids, explanation, suggested_fix), through --set-file. Return it.`)
      } else {
        closed = true
        instr.push(`The review loop ends (verdict ${verdict}, ${fixes} fix round(s); D33). Freeze reference_check and write verifiers/reference_check/status.json: status usable or unusable by D64's rule on the last validation, fix rounds, reasons. Return no further reference-check prompt.`)
      }
    }
    const h = await register(`round${k}`, outs, `P5, round ${k}. State: ${state}. ${instr.join(' ')}`)
    if (halted(h)) return finish(false)
    pending = h.next_prompts || []; state = h.state
  }
  const close = rec('close', await host('close', `P5 closing. State: ${state}. The review loop ${closed ? 'ended' : 'did not end normally'} with ${fixes} fix round(s). Make sure reference_check and independent_label are frozen with their status.json records; if one is not, freeze it now with the status its last validation gives and say why. Check every frozen_at. Return no next_prompts.`))
  return finish(!halted(close) && closed)
}

if (PH === 'P6') {
  const h = await simplePhase(
    `P6 preparation. First check the order (F7, D65): git show origin/claude/new-session-2khocq:data/manifests/natural_phase_ends.jsonl must hold ${T}'s P5 line, and every verifier of the task (task.json and verifiers_extra.json) must be frozen with a frozen_at earlier than now; stop if either fails. Then fix the near-miss targets from the frozen reference contract by D64 decision 14 (write them, with the rule applied, to ${RR}/targets.json); build the five pool workspaces (eval-alt-1 and eval-alt-2 with role alternative; eval-nm-1, eval-nm-2 and eval-nm-3 with role near-miss); and render their prompts (altimpl:v1-natural variants eval-alt-1 and eval-alt-2, with TESTS; nearmiss:v1-natural own-target or shared-target, with TARGET). Return the five prompts.`,
    `P6 registration. For each pool run: verify its prompt and make its generation record; its started_at must be later than every verifier's frozen_at (check it, and stop if not). Register as the altimpl and nearmiss templates' headers say: add-candidate <task>-eval-alt-<k> --origin valid_alternative --split eval --state-dir <workspace>/repo --produced-by altimpl:v1:reference:eval:<k> --label valid --labeler altimpl:v1 --labeler-kind construction; add-candidate <task>-eval-nm-<k> --origin constructed_near_miss --split eval --state-dir <workspace>/repo --produced-by nearmiss:v1:reference:eval --label invalid --violates <its TARGET> --labeler nearmiss:v1 --labeler-kind construction; each with its description taken from the agent's answer by a script and its generation record. If a near miss names another requirement than its TARGET as the one it violates, register it with its TARGET, keep its own words in the description, and report it. Return no next_prompts.`)
  return finish(!halted(h))
}

if (PH === 'P7') {
  const h = await simplePhase(
    `P7 preparation. Build the two mapper workspaces (role mapper, named mapper-1 and mapper-2) and render the mapper:v1-natural prompts (variants mapper-1 and mapper-2). Return both.`,
    `P7 registration. Verify the mappers' prompts and make their generation records. Copy their files as the mapper template's header says (mapper-1 to the task's contracts/mapping_initial_only.json and mapping_full_session.json, mapper-2 to mapping2_*.json), recording any correction. Run scripts/find_duplicates.py on the task. Then the audits (D64, "Audits"): every natural agent's transcript of this family (each workspace of the D64 table, re-runs included) with scripts/audit_eval_generators.py --task-dir ${TD} --profile natural, and the labeler writer and its revision also with the labeler profile of scripts/strict_reaudit.py (--tasks-root data/natural/tasks). Read every flag in its transcript and write its assessment into labels/generator_audit.json as D64 says. Run validate-task, and tracecontract natural-index --out ${RR}/natural_index_check.json (never the committed index). Report the family's state: contracts, verifiers (frozen, status), candidates, audit verdicts, and anything not done. Return no next_prompts.`)
  return finish(!halted(h))
}
return finish(false)
