export const meta = {
  name: 'skillrun-step4',
  description: 'Run Steps 1-3 across N use cases, gate each phase, capture structured feedback, stop at push',
  phases: [
    { title: 'Provision' }, { title: 'Baseline' }, { title: 'Boot' },
    { title: 'Integrate' }, { title: 'Verify' }, { title: 'Consolidate' },
  ],
}

// ===================== constants & gates (§4) =====================
const MAX_RETRIES = 5
const BATCH = 3   // 3 use cases in flight at a time (capacity plan §2)

const GATE = {
  baseline:   r => r?.buildExitCode === 0 && !!r?.committedSha,
  baselineUp: b => (b?.dockerUp || b?.emulatorUp) && b?.allServicesHealthy && b?.loginSmokePassed,
  integrate:  r => r?.compileExitCode === 0,
  integratedUp: v => (v?.dockerUp || v?.emulatorUp) && v?.allServicesHealthy && v?.sdkInitOk === true,
}

// ===================== use-case matrix (STEP4_USE_CASES.md) =====================
// Pilot: USE_CASES.slice(0,1) ; full sweep: all 10. slug = §6.1 namespace prefix.
// archetype: N=native-split (web+android+ios) · R=RN-split (web+mobile) · F=Flutter-unified (app)
const ALL_USE_CASES = [
  { slug:'mkt', name:'Marketplace',       repo:'step4-marketplace',       archetype:'R', web:'Next.js',    android:'React Native (Expo)', ios:'React Native (Expo)', backend:'Python',        skills:['nextjs-patterns','native-expo'] },
  { slug:'com', name:'Community forum',   repo:'step4-community-forum',   archetype:'F', web:'Flutter v6', android:'Flutter v6',          ios:'Flutter v6',          backend:'PHP',           skills:['flutter-v6'] },
  { slug:'del', name:'Delivery',          repo:'step4-delivery',         archetype:'N', web:'Angular',    android:'Android Compose (v6)', ios:'iOS (Swift)',        backend:'Node',          skills:['angular','android-v6-compose','ios'] },
  { slug:'dat', name:'Dating',            repo:'step4-dating',           archetype:'R', web:'React',      android:'React Native (bare)',  ios:'React Native (bare)', backend:'Python',        skills:['react','native-bare'] },
  { slug:'fin', name:'Fintech support',   repo:'step4-fintech-support',  archetype:'N', web:'Vue 3',      android:'Android Compose (v6)', ios:'iOS (Swift)',        backend:'Java (Spring)', skills:['vue-GAP','android-v6-compose','ios'] },
  { slug:'cre', name:'Creator community', repo:'step4-creator-community',archetype:'N', web:'Astro',      android:'Android Kotlin (v5)',  ios:'iOS (Swift)',        backend:'Go',            skills:['astro-patterns','android-v5','ios'] },
  { slug:'fld', name:'Field-service',     repo:'step4-field-service',    archetype:'F', web:'Flutter v5', android:'Flutter v5',          ios:'Flutter v5',          backend:'PHP',           skills:['flutter-v5'] },
  { slug:'rea', name:'Real-estate',       repo:'step4-real-estate',      archetype:'N', web:'Angular',    android:'Android Kotlin (v5)',  ios:'iOS (Swift)',        backend:'Golang',        skills:['angular','android-v5','ios'] },
  { slug:'rid', name:'Rideshare',         repo:'step4-rideshare',        archetype:'R', web:'Next.js',    android:'React Native (bare)',  ios:'React Native (bare)', backend:'Node',          skills:['nextjs-patterns','native-bare'] },
  { slug:'evt', name:'Event platform',    repo:'step4-event-platform',   archetype:'N', web:'Vue 3',      android:'Android Compose (v6)', ios:'iOS (Swift)',        backend:'Java (Spring)', skills:['vue-GAP','android-v6-compose','ios'] },
]
// Folder skeleton per archetype (created at repo init, §D1).
const LAYOUT = {
  N: ['web','android','ios','backend'],   // 3 frontend codebases + backend
  R: ['web','mobile','backend'],          // web + shared RN (android+ios) + backend
  F: ['app','backend'],                   // single Flutter codebase (web+android+ios) + backend
}

// `args.segment` = 'A' | 'B' | 'C' ; `args.pilot` = true -> slice(0,1). Default segment A, pilot on.
const PILOT   = args?.pilot !== false
const SEGMENT = args?.segment || 'A'
const USE_CASES = PILOT ? ALL_USE_CASES.slice(0, 1) : ALL_USE_CASES

// ===================== schemas (§5) =====================
const BASELINE_SCHEMA = { type:'object', required:['useCase','buildExitCode','outputTail'], properties:{
  useCase:{type:'string'}, stack:{type:'string'}, buildExitCode:{type:'number'},
  repoName:{type:'string'}, repoUrl:{type:'string'}, repoCreated:{type:'boolean'},  // §D1 — created, NOT pushed
  committedSha:{type:'string'}, outputTail:{type:'string'} } }

const BOOT_SCHEMA = { type:'object', required:['useCase','allServicesHealthy','loginSmokePassed'], properties:{
  useCase:{type:'string'}, ucSlug:{type:'string'}, dockerUp:{type:'boolean'}, emulatorUp:{type:'boolean'},
  servicesHealthy:{type:'array',items:{type:'object'}}, allServicesHealthy:{type:'boolean'},
  loginSmokePassed:{type:'boolean'}, teardownDone:{type:'boolean'}, diskFreedMB:{type:'number'},
  bootEvidenceTail:{type:'string'} } }

const APP_CONFIG_SCHEMA = { type:'object', required:['appId','region'], properties:{
  appId:{type:'string'}, region:{type:'string'}, extensionsEnabled:{type:'array',items:{type:'string'}},
  webhookSet:{type:'boolean'}, pushKeysRegistered:{type:'boolean'}, dashboardResidue:{type:'array',items:{type:'string'}} } }

const RUN_SCHEMA = { type:'object', required:['useCase','platform'], properties:{
  useCase:{type:'string'}, platform:{type:'string'}, uikitVersion:{type:'string'}, compileExitCode:{type:'number'},
  activation:{type:'object'}, outcome:{type:'object'}, effort:{type:'object'}, docsMcp:{type:'object'},
  summary:{type:'object'}, issues:{type:'array'}, gaps:{type:'array'} } }

const VERDICT_SCHEMA = { type:'object', required:['integratedUp','refuted'], properties:{
  dockerUp:{type:'boolean'}, emulatorUp:{type:'boolean'}, allServicesHealthy:{type:'boolean'},
  sdkInitOk:{type:'boolean'}, integratedUp:{type:'boolean'}, cometchatUsersSeeded:{type:'number'},
  refuted:{type:'boolean'}, reason:{type:'string'}, retryCount:{type:'number'},
  dockerCleanupDone:{type:'boolean'}, diskFreedMB:{type:'number'}, evidenceTail:{type:'string'} } }

const CONSOLIDATED_SCHEMA = { type:'object', properties:{
  failurePatternsByPlatform:{type:'object'}, mostFrequentHallucinations:{type:'array'},
  worstCoveredUseCases:{type:'array'}, perPlatformEaseScores:{type:'object'}, issueRollup:{type:'array'},
  gapRollup:{type:'array'}, docsMcpCoverage:{type:'array'}, rankedFixBacklog:{type:'array'}, needsAttention:{type:'array'} } }

const needsAttention = []

// ========================================================================
// SEGMENT A — Baseline -> Boot & Verify  (halts at CP1)
// ========================================================================
if (SEGMENT === 'A') {
  phase('Baseline')
  const booted = []
  for (let i = 0; i < USE_CASES.length; i += BATCH) {
    const batch = USE_CASES.slice(i, i + BATCH)
    const res = await pipeline(batch,
      uc => agent(`Build baseline "${uc.name}" — web:${uc.web}, android:${uc.android}, ios:${uc.ios}, backend:${uc.backend}.\n`
        + `STEP 0 — REPO (§D1, create-only): run \`gh repo create ${uc.repo} --private\` (empty, private). Do NOT use --push. `
        + `Locally: git init, git branch -M main, git remote add origin <the new repo>. Scaffold the archetype folders `
        + `[${LAYOUT[uc.archetype].join(', ')}] + docker-compose.yml + .env.example (standard COMETCHAT_* names, UC_SLUG=${uc.slug}) + .gitignore.\n`
        + `STEP 1 — BUILD: realistic app with RBAC roles, clean structure, NO CometChat. One REST contract all 3 clients + backend obey.\n`
        + `STEP 2 — GATE: confirm it compiles. Commit locally on main. **Do NOT git push — push is human-gated.**\n`
        + `Return repoName, repoUrl, repoCreated, buildExitCode, committedSha, outputTail.`,
        { label:`baseline:${uc.slug}`, phase:'Baseline', schema: BASELINE_SCHEMA }),
      (base, uc) => {
        if (!GATE.baseline(base)) { needsAttention.push(`gate-fail:baseline:${uc.name}`); throw new Error(`gate-fail:baseline:${uc.name}`) }
        return agent(`Bring the ENTIRE "${uc.name}" system up: docker compose for web+backend; Android emulator (AVD Pixel_10) `
          + `+ iOS simulator against the Dockerized backend. Health-check every service, migrate/seed, run the baseline login smoke `
          + `(login as an RBAC role -> land on dashboard). DO NOT integrate anything. Return BOOT_SCHEMA with machine evidence.`,
          { label:`boot:${uc.slug}`, phase:'Boot', schema: BOOT_SCHEMA })
      })
    res.forEach((boot, k) => booted.push({ uc: batch[k], boot }))
  }
  // 🛑 CP1 — return to human. Review boot evidence + login smoke + screenshots before provisioning/integrating.
  return { segment:'A', cp:'CP1', booted, needsAttention,
    ready: booted.filter(x => GATE.baselineUp(x.boot)).map(x => x.uc.slug) }
}

// ========================================================================
// PROVISION (one-time, post-CP1) + SEGMENT B — Integrate -> Re-Boot & Verify  (halts at CP2)
// ========================================================================
if (SEGMENT === 'B') {
  phase('Provision')
  const appConfig = await agent(
    `Using the CometChat automation keys in .env.pipeline, create/configure the ONE shared app: enable Calls + moderation `
    + `+ reactions + collaborative, set the webhook URL + auth, register FCM/APNs push keys. Emit cometchat-app-config.json. `
    + `Anything the keys can't reach -> COMETCHAT_DASHBOARD_CHECKLIST.md (and that residue is itself a finding).`,
    { label:'provision-app', phase:'Provision', schema: APP_CONFIG_SCHEMA })

  phase('Integrate')
  const booted = args?.booted || []                 // passed from Segment A's return
  const passed = booted.filter(x => GATE.baselineUp(x.boot))
  const runs = []
  for (let i = 0; i < passed.length; i += BATCH) {
    const slice = await pipeline(passed.slice(i, i + BATCH),
      ({ uc }) => {
        if (budget.total && budget.remaining() < 60_000) throw new Error(`budget-cut:${uc.name}`)
        return agent(`On branch cometchat-integration, integrate CometChat into "${uc.name}" via PINNED skills + docs-mcp `
          + `across web(${uc.web}) + Android(${uc.android}) + iOS(${uc.ios}) + backend(${uc.backend}). Namespace every UID/GUID `
          + `with slug "${uc.slug}". Instrument for telemetry. Commit locally (NO push).\n`
          + `GAP LOG (required): write pipeline-state/gaps/${uc.slug}.md with a "## ${uc.name} (${uc.slug})" heading, then one `
          + `bullet per gap using EXACT tag markers so the aggregator counts them: docs-mcp -> "coverageGap: \\"<verbatim query>\\"", `
          + `"staleness: <doc> vs <sdk>", "docsEscape: <topic>"; skills -> "missedTrigger: <platform/version>", `
          + `"falseTrigger: <skill>", "variant: chose <x> want <y>", "hallucination: <API/class/prop>". `
          + (uc.skills.includes('vue-GAP') ? `The Vue 3 web slice has NO cometchat-vue skill — record "missedTrigger: vue-web" (expected). ` : ``)
          + `If a slice had zero gaps, write "- none". Return RUN_SCHEMA per platform.`,
          { label:`integrate:${uc.slug}`, phase:'Integrate', schema: RUN_SCHEMA })
      },
      (run, { uc }) => {
        if (!GATE.integrate(run)) { needsAttention.push(`gate-fail:integrate:${uc.name}`); throw new Error(`gate-fail:integrate:${uc.name}`) }
        return agent(`STEP 1 — Re-boot the INTEGRATED "${uc.name}" system; confirm every service healthy AND the CometChat SDK `
          + `inits with no error (integratedUp/sdkInitOk). If it won't boot, STOP — skills-tagged blocker; do not test calls. `
          + `STEP 2 — seed ~4-6 CometChat users, every UID/GUID prefixed "${uc.slug}-" (no deletion — quota raised). `
          + `STEP 3 — run the fixed e2e (login->chat->call) on web+Android+iOS, correct & re-run up to ${MAX_RETRIES}x `
          + `(report retryCount), then adversarially REFUTE it works. STEP 4 — docker compose down -v + prune to FREE DISK. `
          + `If the integrated system won't boot, APPEND "- skills-blocker: won't boot" to pipeline-state/gaps/${uc.slug}.md `
          + `(a modified system that won't boot is a skills-tagged finding, §2). Return VERDICT_SCHEMA + score.`,
          { label:`verify:${uc.slug}`, phase:'Verify', schema: VERDICT_SCHEMA })
      })
    slice.forEach((v, k) => runs.push({ uc: passed[i + k].uc, verdict: v }))
  }
  // rebuild the live gaps ledger from the section files the integrate/verify agents wrote
  await agent(`Run: bash scripts/build-master-gaps.sh . Then read MASTER_GAPS.md and return its rollup counts line.`,
    { label:'gap-tracker', phase:'Verify' })
  // 🛑 CP2 — return to human. Review chat/call e2e + diff + verdict per platform before consolidate + push.
  return { segment:'B', cp:'CP2', appConfig, runs, needsAttention }
}

// ========================================================================
// SEGMENT C — Consolidate (barrier, once, after all runs clear CP2)
// ========================================================================
if (SEGMENT === 'C') {
  phase('Consolidate')
  const runs = args?.runs || []
  const consolidated = await agent(
    `Aggregate these ${runs.length} runs plus the existing Deskline/Telehealth/Edtech feedback docs. Dedupe issues by `
    + `ISS-*/G-* id, rank by frequency×severity, list top fixes for cometchat-skills and docs-mcp, and collect everything `
    + `that hit the needsAttention channel. Emit CONSOLIDATED_SCHEMA -> report.`,
    { label:'consolidate', phase:'Consolidate', schema: CONSOLIDATED_SCHEMA })
  return { segment:'C', consolidated }
}

throw new Error(`unknown segment: ${SEGMENT} (expected A|B|C)`)
