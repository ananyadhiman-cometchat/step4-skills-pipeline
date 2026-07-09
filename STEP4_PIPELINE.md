# STEP4_PIPELINE.md — Iterative Skills Reviewer, Step 4

> **Deliverable 4:** the reusable agentic pipeline that runs Steps 1–3 across many use cases and aggregates the feedback. This doc is the **contract the orchestrating agent follows** — phases, testing methods, gates, and conditions. Nothing here pushes to GitHub: **the agent commits locally; push and PR are human-gated (owner access only).**

---

## 0. How to run (pilot first, then scale)

1. **Pilot — `N = 1`.** Run the pipeline over a **single** use case end-to-end. Confirm: gates fire, e2e runs, retries are bounded, telemetry is structured, the dashboard renders, commits land locally, and it stops at the push boundary. *Only the `USE_CASES` array changes between pilot and full run.*
2. **Full — `N = 10`.** Swap in all ten use cases. Same script, same gates.

This pilot-then-scale path is why the use-case list is a plain array: `USE_CASES.slice(0,1)` for pilot, full array for the real sweep.

---

## 1. Use-case matrix

**Already done (feed the consolidation, NOT re-run):** Deskline (helpdesk · React/Vite+Flutter v5 · Node) · Telehealth (RN Expo · Go) · Educator/Edtech (Angular · Node).

**To RUN (10) — every use case ships web + Android + iOS; tech varied across the set.** Full matrix (with per-platform stacks + codebase counts) lives in [STEP4_USE_CASES.md](STEP4_USE_CASES.md). Summary:

| # | Use case | Web | Android | iOS | Backend | Frontend skills |
|---|---|---|---|---|---|---|
| 1 | Marketplace | Next.js | React Native (Expo) | React Native (Expo) | Python | `nextjs-patterns`, `native-expo` |
| 2 | Community forum | Flutter v6 | Flutter v6 | Flutter v6 | PHP | `flutter-v6` |
| 3 | Delivery | Angular | Android Compose (v6) | iOS (Swift) | Node | `angular`, `android-v6-compose`, `ios` |
| 4 | Dating | React | React Native (bare) | React Native (bare) | Python | `react`, `native-bare` |
| 5 | Fintech support | Vue 3 | Android Compose (v6) | iOS (Swift) | Java (Spring) | **`vue` (gap)**, `android-v6-compose`, `ios` |
| 6 | Creator community | Astro | Android Kotlin (v5) | iOS (Swift) | Go | `astro-patterns`, `android-v5`, `ios` |
| 7 | Field-service | Flutter v5 | Flutter v5 | Flutter v5 | PHP | `flutter-v5` |
| 8 | Real-estate | Angular | Android Kotlin (v5) | iOS (Swift) | Golang | `angular`, `android-v5`, `ios` |
| 9 | Rideshare | Next.js | React Native (bare) | React Native (bare) | Node | `nextjs-patterns`, `native-bare` |
| 10 | Event platform | Vue 3 | Android Compose (v6) | iOS (Swift) | Java (Spring) | **`vue` (gap)**, `android-v6-compose`, `ios` |

*(Flutter = 1 codebase for all 3 platforms; React Native = 1 codebase for Android+iOS; native cells are separate codebases. ~23 frontend codebases total.)*

**Coverage:** Web → Next.js · React · Angular · **Vue 3** · Astro. Cross-platform → Flutter v6/v5 · RN bare/Expo. Native → Android Compose v6 · Android Kotlin v5 · iOS Swift. Backends → Python · PHP · Node · Java (Spring) · Go. UI-Kit v5 **and** v6. Products → 1:1, groups, calls, push, moderation, reactions/polls, RBAC.

> **Vue (runs 5 & 10) is a deliberate frontier probe (verified against CometChat docs):** CometChat ships a **Vue UI Kit**, but there is **no `cometchat-vue` skill** — the sharpest coverage gap. Expect no skill to trigger; **record that as the finding.**
> **iOS is in every use case → the Mac mini builds all 10 iOS targets; the HP builds web + Android.** Each use case splits across both machines by platform (see §6.5).

---

## 2. Phases

Each use case flows through these phases. In `pipeline()` there is **no barrier** between per-item phases (a fast repo can be at Verify while a slow one is still at Baseline); the only barrier is **Consolidate**, which needs all runs.

| Phase | Agent does | Skill leveraged | Output |
|---|---|---|---|
| **Baseline** | Build the realistic app (RBAC roles, clean structure), **no CometChat**. Confirm it **compiles**. Commit locally on `main`. | `Explore`/`Plan` to scaffold | `BASELINE_SCHEMA` (build evidence) |
| **Boot & Verify** 🔴 | **Bring the entire system up and prove it runs** — `docker compose up` (web+backend, as Deskline does) or emulator boot (mobile) → health-check every service → run the baseline **login smoke** (login as an RBAC role → land on dashboard). **This is the false-positive guard: integration only starts on a confirmed-healthy baseline.** | `verify` (run the app & observe) | `BOOT_SCHEMA` (runtime evidence) |
| **Integrate** | *(only if the baseline booted healthy)* On branch `cometchat-integration`, integrate CometChat via **pinned** skills + docs-mcp into every frontend/backend. Instrumented for telemetry. Commit locally. | `cometchat-*` (under test) | `RUN_SCHEMA` |
| **Re-Boot & Verify** 🔴 | **First re-boot the *integrated* system** (`docker compose up` with the new CometChat code + envs; emulator for mobile) and health-check it — services green **and the CometChat SDK inits without error** — *before any chat/call test*. Only then run the full e2e (login→chat→call), correct & retry (bounded), and adversarially refute "it works". A modified system that won't boot is a **`skills`**-tagged finding. | `verify`, `/code-review`, `security-review` | `VERDICT_SCHEMA` + final score |
| **Consolidate** *(barrier)* | Aggregate all runs + the 3 done docs into: failure patterns by platform, most-frequent hallucinations, worst-covered use cases, and a **ranked skill/docs fix backlog** (each fix tied to the blocker that motivated it). | — | `CONSOLIDATED_SCHEMA` → report |

### 2.1 Subagents inside each phase (document-driven — no monolithic "build agent")

Each phase **fans out to specialized subagents** that hand structured **artifacts** to the next: `requirements.md → research.md → design.md → code → tests → report`. Every artifact persists (in the repo or `pipeline-state/`) so each step is inspectable and feeds the next — this is also *where* the metrics are captured (noted per agent).

**Phase 1 — Baseline** (build the app, no CometChat)
| Subagent | Does | Output / captures |
|---|---|---|
| `req:baseline` | Requirements — features, RBAC roles, user stories, tri-platform scope | `requirements.md` |
| `design:baseline` | Architecture — data model, **one REST API contract all 3 clients + backend obey**, per-platform screen/component map, folder layout | `design.md` |
| `build:backend` | Backend + schema + namespaced seed (~6 users) | code + `buildExitCode` |
| `build:web` · `build:android` · `build:ios` | **Parallel** — each scaffolds its platform against the contract | code per platform |
| `compile:*` | Typecheck/build gate per artifact | `buildExitCode` (feeds `GATE.baseline`) |

**Phase 2 — Boot & Verify**
| Subagent | Does | Output |
|---|---|---|
| `boot:baseline` | Docker up (backend+web) + Android emulator + iOS simulator → health-check → login smoke | `BOOT_SCHEMA` |

> ### 🛑 CHECKPOINT CP1 — human verification (pipeline PAUSES here)
> After Boot & Verify, the pipeline **halts** and hands you a review packet (boot evidence, login-smoke result, screenshots per platform). **You confirm the baseline app genuinely works** before any CometChat is provisioned/integrated. Resume to continue. *(No point provisioning + integrating on a baseline you haven't eyeballed.)*

**Phase 2.5 — App provisioning** *(one-time, runs right after the FIRST baseline passes CP1 — CometChat automation keys)*
| Subagent | Does | Output |
|---|---|---|
| `provision-app` | Use the automation keys to create/configure the ONE shared CometChat app — enable extensions (Calls, moderation, reactions), set the webhook URL, register push keys. Runs **once** for the whole sweep. | `cometchat-app-config.json` |

**Phase 3 — Integrate** (the skills-review core)
| Subagent | Does | Output / captures |
|---|---|---|
| `req:integrate` | Which CometChat products per use case, RBAC→CometChat mapping, mount points per platform | `cometchat-requirements.md` |
| `research:cometchat` | **The docs-mcp + skills exerciser** — query cometchat-skills + docs-mcp for the right recipe per platform/version | `cometchat-research.md` · **captures 5.1 skill-activation + 5.4 docs-mcp metrics** |
| `design:integrate` | Namespaced UID scheme, auth-token endpoint, group model, webhook handlers, env plan | `cometchat-integration-plan.md` |
| `integrate:backend` | Auth-token endpoint, user sync, webhook handler, REST client | code |
| `integrate:web` · `integrate:android` · `integrate:ios` | **Parallel** — each uses its platform cometchat-skill | code · **captures 5.3 effort + hallucinations per platform** |
| `review:diff` | `/code-review` + `security-review` (secret scan) on the integration diff | **`diffQuality` (5.2)** |

**Phase 4 — Re-Boot & Verify**
| Subagent | Does | Output |
|---|---|---|
| `reboot:integrated` | Boot integrated system, SDK-init check, seed namespaced CometChat users | re-boot proof |
| `e2e:web` · `e2e:android` · `e2e:ios` | **Parallel** — run login→chat→call per client; bounded retry (`MAX_RETRIES`) | pass/fail + `retryCount` |
| `verify:refute` | Adversarial verifier per platform — must fail to refute "chat+call works" | `VERDICT_SCHEMA` |
| `teardown` | **`docker compose down -v` + prune** to free disk (the only space lever now). **CometChat users are NOT deleted** — quota expanded, so seeded namespaced users just persist. | `dockerCleanupDone`, `diskFreedMB` |
| `report:run` | Assemble `RUN_SCHEMA` from all artifacts + transcripts | per-run report |

> ### 🛑 CHECKPOINT CP2 — human verification (pipeline PAUSES here)
> After Re-Boot & Verify, the pipeline **halts** and hands you the integrated-run packet (chat/call e2e result per platform, the diff, the verdict, screenshots). **You confirm the integration actually works** before consolidation and before you push. Resume to continue.

**Phase 5 — Consolidate** *(barrier, once — after all runs clear CP2)*
| Subagent | Does | Output |
|---|---|---|
| `consolidate` | Aggregate all runs + the 3 done docs | `CONSOLIDATED_SCHEMA` |
| `critic:completeness` | "What's missing — unverified claim, skipped platform, unrun query?" → next-round work | gap list |

**Concurrency:** **3 use cases in flight at a time** (capacity plan); within a use case the `*:web / *:android / *:ios` agents run in parallel. The Workflow cap `min(16, cores−2)` still bounds total live agents.

---

## 3. Testing methods (the e2e gate)

The **fixed e2e flow across all use cases** is: **login as an RBAC role → open a chat → send a message → start a call**. Only the surrounding app changes, so scores are comparable.

| Platform | Build gate | E2E method |
|---|---|---|
| Next.js / React / Angular | `npm run build` exit 0 | **Playwright** — headless, runs the fixed flow |
| React Native (bare) / Flutter | platform build | **Detox** / Flutter `integration_test` on emulator |
| Android (Compose v6 / Kotlin v5) | `assembleDebug` | **Maestro** flow |
| iOS (Swift) | `xcodebuild` | **Maestro** / XCUITest |
| JSP (Java) | `mvn package` | **Playwright** against the served page |
| Backend (Python/PHP/Node/Go/Java) | build/compile exit 0 | hit `/auth-token`, user-sync, webhook → assert token minted + user synced |

### Boot & Verify method — how "the system is actually up" is proven

**Docker is the default boot mechanism for every run's server side**, mirroring Deskline (`docker-compose.yml`). The gate needs *runtime* evidence, not a build log.

| Stack part | Boot | Health evidence required |
|---|---|---|
| Backend (Node/Python/Go/PHP/Java/JSP) | `docker compose up -d` | container `healthy` + `/health` (or equiv) returns 200 + DB migrated/seeded |
| Web frontend (React/Next/Angular/Astro) | in the same compose (or `dev` server container) | served page returns 200 + **login smoke** passes (Playwright) |
| Mobile (Android/iOS/Flutter/RN) | app on **emulator/simulator**, pointed at the **Dockerized backend** | app launches → login screen renders → login succeeds against the live backend |

So: **Docker for all backends + web** (same as Deskline use-case 1); **emulator/simulator for the mobile client**, but its backend is still the Docker stack. A run only leaves Boot & Verify when the whole system is confirmed live — otherwise it's a baseline failure, tagged `agent` (baseline build), **never** `skills`.

Reuse the `cometchat-skills` **`test-suite/` verify scripts** where they exist — `verify.sh`, the **typecheck-fences** (build/compile pass), and **AST checks** (symbol exists → catches hallucinated APIs) — rather than re-inventing them. Those feed `buildPassRate`, `hallucinationCount`, and `runtimeSuccess` directly.

Every gate result is **machine evidence** (exit code, tests-passed count, last 20 lines of output) written into the schema — never the agent's self-assessment.

---

## 4. Gates & conditions (the agent MUST obey)

```
GATE.baseline(r)   ⇒  r.buildExitCode === 0 && r.committedSha exists
GATE.baselineUp(b) ⇒  b.dockerUp === true (or b.emulatorUp) && b.allServicesHealthy === true
                      && b.loginSmokePassed === true          // ← the false-positive guard
GATE.integrate(r)  ⇒  r.compileExitCode === 0
GATE.integratedUp(v) ⇒ (v.dockerUp || v.emulatorUp) && v.allServicesHealthy && v.sdkInitOk === true
                        // modified system must boot BEFORE chat/call is tested; fail here → tag `skills`
GATE.verify(v)     ⇒  v.integratedUp === true && v.refuted === false
```

**Rules:**
1. **Gate before advancing.** Each phase asserts the previous gate at its top; if false → `throw` (drops this use case cleanly to a recorded "stopped at <phase>", skips remaining phases). **Integrate must not start unless `GATE.baselineUp` passed** — no integrating on a dead baseline.
2. **Bounded retries.** The Verify→Integrate correction loop has `MAX_RETRIES = 5`. On exhaustion: stop, set `outcome: "retries-exhausted"`, **score = 1**, move on. *An integration the agent cannot finish is the most valuable finding — record it, never spin.*
3. **Budget guard.** Each use case is cut off at its token slice: `budget.total && budget.remaining() > 60_000`. Prevents one pathological repo eating the sweep.
4. **Hallucination checks.** (a) Any CometChat symbol used is cross-checked against the skill component catalog / docs-mcp; unknown symbol → `hallucinatedAPIs[]`. (b) An adversarial **verifier agent** must fail to refute success before Verify passes.
5. **needsAttention channel.** Gate-fail, retries-exhausted, hallucinated-API, or a dead subagent (`agent()` returns `null`) → pushed to `needsAttention[]` and `log()`-ed. Non-blocking (background can't prompt); surfaced for human review.
6. **Commit/push.** Agent runs `git commit` on `main` and `cometchat-integration` locally. **No `git push`, no `gh pr create` inside any agent** — those are the human's foreground step. A pre-push secret-scan blocks if `REST_API_KEY`/tokens appear in the diff.
7. **Human checkpoints (hard pauses).** The pipeline **halts** twice for human verification: **CP1** after Boot & Verify (confirm the baseline actually runs before provisioning/integrating) and **CP2** after Re-Boot & Verify (confirm chat/call works before consolidate + push). Implemented as segmented runs (§7) — the workflow returns a review packet, the human approves in chat, and `resume` launches the next segment (finished work is cached, nothing re-runs).

---

## 5. Metrics contract (the authoritative per-run report)

Every run emits these — the brief's **Skills Metrics**, verbatim in structure so results are comparable across use cases, platforms, and skill versions. They **extend the existing `test-suite/` harness** in `cometchat-skills` (which already covers *framework × experience × project-type × model × IDE* with typecheck / AST / E2E verify scripts); the pipeline records those same dimensions **plus** everything below. Each metric notes its capture source so the agent knows where the value comes from.

### 5.1 — Skill activation *(source: agent transcript)*
| Metric | Definition |
|---|---|
| `triggerAccuracy` | Correct skill(s) invoked for the platform/version **without being named explicitly** |
| `variantSelection` | Right variant chosen (`android-v6-compose` vs `android-v5`, flutter v5 vs v6, …) |
| `falseTriggers[]` / `missedTriggers[]` | Irrelevant skill loaded, or no skill loaded when one exists |

### 5.2 — Integration outcome *(source: CI / `verify.sh` + typecheck-fences + PR review)*
| Metric | Definition |
|---|---|
| `buildPassRate` | App compiles/builds after integration, per platform |
| `runtimeSuccess` | Launches; login, conversation list, 1:1 send/receive work; calls connect (if in scope) |
| `featureCompleteness` | % of requested scope implemented (auth-token flow, RBAC user mapping, push, theming) — **checklist vs PR diff** |
| `diffQuality` | Minimal & idiomatic; no unrelated refactors, **no secrets committed**, keys in env config |

### 5.3 — Agent effort *(proxy for skill quality; source: run log)*
| Metric | Definition |
|---|---|
| `firstPassSuccess` | Integration worked with **no** human correction (Y/N) |
| `retryCount` | Error-fix loops before build+run passed (bounded by `MAX_RETRIES`) |
| `hallucinationCount` + `hallucinatedAPIs[]` | Non-existent APIs/classes/props/packages generated (compile errors + PR review) |
| `docsEscapes` | Times the agent left skills/docs-mcp to web-search or guess |
| `timeMinutes`, `tokens` | Wall-clock and token cost per platform integration (harness telemetry) |

### 5.4 — docs-mcp retrieval *(source: transcript sampling + MCP logs)*
| Metric | Definition |
|---|---|
| `answerRelevance` | Top results answered the actual query — rate **1–5** |
| `coverageGaps[]` | Queries returning nothing useful — **log the query verbatim** |
| `stalenessConflicts[]` | Docs contradicting current SDK versions or the skills |

### 5.5 — Per-run summary
| Metric | Scale |
|---|---|
| `easeScore` | **1–5** per platform (1 = manual rewrite needed, 5 = worked first pass) |
| `blockers[]` | Every issue that stopped progress, tagged **`skills` / `docs-mcp` / `SDK` / `agent`** |
| `improvements[]` | Concrete skill/doc edits, each **tied to the blocker that motivated it** |

### Schemas (mirror the tables above)

```
BASELINE_SCHEMA = { useCase, stack, buildExitCode, committedSha, outputTail }

BOOT_SCHEMA = { useCase, ucSlug, dockerUp, emulatorUp, servicesHealthy[{name,status,healthCheck}],
                allServicesHealthy, loginSmokePassed,        // baseline app only — no CometChat users yet
                teardownDone, diskFreedMB, bootEvidenceTail }   // storage + runtime proof

RUN_SCHEMA = {
  useCase, platform, uikitVersion,
  activation:   { triggerAccuracy, variantSelection, falseTriggers[], missedTriggers[] },
  outcome:      { buildPassRate, runtimeSuccess, featureCompleteness, diffQuality },
  effort:       { firstPassSuccess, retryCount, hallucinationCount, hallucinatedAPIs[],
                  docsEscapes, timeMinutes, tokens },
  docsMcp:      { answerRelevance, coverageGaps[], stalenessConflicts[] },
  summary:      { easeScore, blockers[{desc, tag}], improvements[{edit, motivatedByBlocker}] },
  issues[{id,hit}], gaps[]   // reuse Deskline's ISS-*/G-* ids for rollup
}

VERDICT_SCHEMA = { dockerUp, emulatorUp, allServicesHealthy, sdkInitOk, integratedUp,  // re-boot proof
                   cometchatUsersSeeded,          // namespaced; NOT deleted (quota expanded)
                   refuted, reason, retryCount, dockerCleanupDone, diskFreedMB, evidenceTail }

CONSOLIDATED_SCHEMA = {
  failurePatternsByPlatform{}, mostFrequentHallucinations[], worstCoveredUseCases[],
  perPlatformEaseScores{}, issueRollup[{id,hits,severity}], gapRollup[],
  docsMcpCoverage[], rankedFixBacklog[{fix, tag, motivatedBy, frequency}], needsAttention[]
}
```

> **Capture note:** transcript-sourced metrics (activation, docs-escapes) are self-reported by the integration agent **and** spot-verified — the agent has no incentive to flatter the skills, and the adversarial verifier + compile logs catch inflated `runtimeSuccess`/`firstPassSuccess` claims.

---

## 6. Standardization — CometChat app, dashboard, envs & Docker

### 6.1 One shared CometChat app for all 10 runs — collisions avoided by namespacing + smart seeding
**Decision:** a single CometChat app for the whole sweep (one manual dashboard setup, one creds set). The two risks a shared app creates are handled deterministically:

**A. Namespace everything by use-case slug → no collisions.** A shared app puts all UIDs, group GUIDs, and tags in one namespace, so identity must be prefixed:
- **UIDs:** `<slug>-<role><n>` — e.g. `mkt-admin`, `del-driver1`, `dat-cust2` (never bare `admin`/`1`).
- **Group GUIDs:** `<slug>-<name>` — e.g. `mkt-ticket-1`, `evt-room-3`.
- **Tags:** carry the use case too — `uc:marketplace`, plus `role:*` / `dept:*`.
- The Baseline seed script for each repo applies its own prefix, so two runs can never clash.

**B. User quota — expanded, so no deletion needed.** Quota has been raised (access to more users granted), so the pooled 100-user cap is no longer the binding constraint. Therefore:
- **Seed tiny + namespaced anyway:** ~4–6 users per use case (one per RBAC role + a couple of participants), every UID/GUID `UC_SLUG`-prefixed. Tidy and collision-free.
- **No teardown deletion of CometChat users** — seeded users just persist across the sweep. The only thing torn down at teardown is **Docker** (see §6.4), which is the real space concern now.

**C. Two shared-app limitations to accept (and log if they bite):**
- **One webhook URL for the whole app.** Each use case has its own backend, but the app has a single webhook config — so real webhook *delivery* can only be validated for whichever run currently owns the URL (point it at the run in its Verify window). Other runs verify webhook *handling* against synthetic payloads. *If this blocks a run, it's a `docs`/`SDK` note, not a skills failure.*
- **Shared extension config.** Enable the union of needed extensions (AI Moderation, Calls, Collaborative, Reactions…) once; all runs see the same set. Fine for a smoke sweep.

(Verified against `docs/fundamentals/multi-tenancy-overview` — multi-tenancy remains the collision-free alternative if you later want per-run isolation; this sweep deliberately trades that for one-time setup.)

### 6.2 What can be automated vs manual — with automation keys, provisioning is now agent-driven
**Update:** with the CometChat **automation/management keys** (access incoming), app configuration is no longer a manual dashboard step — the `provision-app` subagent (Phase 0, §2.1) does it. What remains where:
- **CometChat MCP server = read-only** (`search_cometchat_docs`, `fetch_cometchat_doc_page`, `get_cometchat_implementation_bundle`; no account/key). Helps *write code*; never configures the app.
- **`provision-app` agent (automation keys):** create/configure the app → capture `APP_ID`/`REGION`/`AUTH_KEY`/`REST_API_KEY`, enable the union of extensions (Calls, moderation, reactions…), set the webhook URL + auth, register FCM/APNs keys. Output `cometchat-app-config.json`. *If any setting is NOT reachable by the keys, that residue goes in `COMETCHAT_DASHBOARD_CHECKLIST.md` — and the gap is itself a finding.*
- **REST API v3 (agent, per run):** namespaced users + roles/tags, groups + members, auth-token minting, and **user cleanup at teardown**.
- **Still human-only:** `git push` / `gh pr create` (owner access) — provisioning automation does **not** change the push gate.

| Task | Automatable? | How |
|---|---|---|
| Create the app + capture keys | ✅ | `provision-app` agent (automation keys) |
| Enable extensions (Calls, Moderation, Collaborative…) | ✅ *(verify in pilot)* | `provision-app` — else `COMETCHAT_DASHBOARD_CHECKLIST.md` residue |
| Webhook URL + auth, FCM/APNs push keys | ✅ *(verify in pilot)* | `provision-app` — else checklist residue |
| Users + RBAC tags, groups, members, auth tokens, teardown cleanup | ✅ | REST API v3 (per-run agent) |
| `git push` / `gh pr create` | ❌ | **human, owner access only** |

→ **Pilot goal:** confirm exactly how much of the config the automation keys reach. Any setting they *can't* touch lands in `COMETCHAT_DASHBOARD_CHECKLIST.md` — **and that residue is itself a recorded `docs`/`skills` finding.**

### 6.3 Env standardization
- **Single source of truth:** `.env.pipeline` (git-ignored) holds the **one shared app's creds** (`APP_ID`, `REGION`, `AUTH_KEY`, `REST_API_KEY`) + shared FCM/APNs keys — plus each repo's **`UC_SLUG`** (the namespace prefix from §6.1).
- Each repo commits a **`.env.example`** with the *same standard var names*; a git-ignored `.env` is templated from `.env.pipeline` at boot, injecting that repo's `UC_SLUG` so its seed script namespaces UIDs/GUIDs correctly.
- **Identical names across every run** (so tooling and the skills behave the same): `COMETCHAT_APP_ID`, `COMETCHAT_REGION`, `COMETCHAT_REST_API_KEY`, `COMETCHAT_AUTH_KEY`, `COMETCHAT_AI_AGENT_UID`, `COMETCHAT_WEBHOOK_SECRET`; public → `VITE_COMETCHAT_*` (web) / `--dart-define` (Flutter) / `BuildConfig` (Android).
- The **secret-scan gate (§4.6)** guarantees only `.env.example` is ever committed.

### 6.4 Smart, phase-scoped Docker — coverage is NOT capped by disk
Containers are only needed during three short windows per use case — **Boot & Verify, Re-Boot & Verify, and the e2e test**. Everything else — Baseline build, Integrate (code generation), Consolidate (metrics) — is pure codegen/CPU and holds **zero** container storage. So disk cost is a function of how many use cases are *inside a boot/e2e window at the same instant*, not how many runs are in flight.

That flips the strategy: **don't cap lanes — cap only the short boot windows, and cap them by real free disk, not a fixed number.**

- **Phase-scoped lifecycle:** each boot stage does `up → health/e2e → down -v`, freeing its volumes immediately. A use case holds storage for minutes, then releases it as it moves on to codegen/metrics — where it costs nothing.
- **Disk-aware admission (dynamic semaphore):** before spinning up, the agent checks real headroom (`docker system df`, `df -h`). Boot proceeds if free space > threshold; else it prunes dangling layers and/or waits for another lane's teardown. **Self-tunes per machine** — the 256 GB Mac mini admits more concurrent boots than the laptop, automatically. No hardcoded stack count.
- **Guaranteed teardown:** `down -v` runs even on failure (report `teardownDone`), so a crashed e2e never leaks containers.
- **Shared cached base images + slim variants + shared Postgres/Redis:** base layers pulled once and reused host-wide; only per-run app layers + ephemeral data cost space, reclaimed on teardown.
- **Targeted prune after each teardown:** drop that stack's dangling layers, keep the shared base cache.

Net: **all 10 stay in flight (full coverage); disk self-regulates the brief boot windows.** Peak disk ≈ (concurrent boots the machine's free space allows) × one slim stack — not ten.

### 6.5 Two-machine fleet — Mac mini + HP laptop (split **by platform**, not by use case)
Every use case now ships web + Android + iOS, so the old "whole use case per machine" split no longer works — **every** use case has an iOS slice that only the Mac can build. Partition **per platform**:

- **Hard constraint: iOS builds require macOS/Xcode** → the **Mac mini builds the iOS target of all 10 use cases** (native Swift *and* Flutter/RN iOS).
- **HP builds web + Android** for all 10 (React/Next/Angular/Vue/Astro + Android Compose/Kotlin + the Android side of Flutter/RN).
- **The backend runs where its clients are being tested** (Docker on the machine driving that platform's e2e); use the shared CometChat app so both machines' clients hit the same users/groups.
- **Per-run report = merge of platform slices.** Each machine writes the platform-specific metrics (web/Android on HP, iOS on Mac) into the run's report; the boot/verify ledger (§6.6) keys by `{useCase, platform}` so slices reconcile. **Consolidate ingests both machines' files.**
- **Disk-aware admission (§6.4) runs independently per machine**, tuned to each one's free space.
- *Sequencing note:* since the Mac is the iOS bottleneck for all 10, it will be the long pole — schedule iOS slices to start early and stream, rather than batching them at the end.

### 6.6 Remembering state across the run (resume + storage tracking)
"Remember while it processes" = a **run-state ledger** the boot/verify agents read and write:

- **`pipeline-state/<useCase>-<platform>.json`** records (per platform slice — web / android / ios): current phase, `containerUp`, `teardownDone`, `diskFreedMB`, gate results, `retryCount`, last commit SHA. Slices reconcile into the run's merged report.
- **Why it matters:** (a) the agent always knows **who currently holds storage**, so disk-admission decisions are correct; (b) **resume** — if a machine reboots or the run is interrupted, the pipeline restarts from the last completed gate instead of re-booting finished lanes; (c) an audit trail that also feeds the metrics.
- **Pairs with the Workflow tool's native resume** (`resumeFromRunId` + journal): completed `agent()` calls return cached results instantly, so re-launching after an interruption skips finished lanes. The ledger covers the *external* Docker state the journal doesn't track.

---

## 7. The Workflow script (skeleton the pipeline runs)

```javascript
export const meta = {
  name: 'skillrun-step4',
  description: 'Run Steps 1-3 across N use cases, gate each phase, capture structured feedback, stop at push',
  phases: [{title:'Provision'},{title:'Baseline'},{title:'Boot'},{title:'Integrate'},{title:'Verify'},{title:'Consolidate'}],
}

const MAX_RETRIES = 5
const GATE = {
  baseline:   r => r?.buildExitCode === 0 && r?.committedSha,
  baselineUp: b => (b?.dockerUp || b?.emulatorUp) && b?.allServicesHealthy && b?.loginSmokePassed,
  integrate:  r => r?.compileExitCode === 0,
}
const USE_CASES = [ /* pilot: .slice(0,1) ; full: all 10 */ ]
const BATCH = 3   // 3 use cases in flight at a time (capacity plan)

// The sweep runs as THREE segments with a HUMAN CHECKPOINT between them. A background
// workflow can't block on human input, so each segment is its own run that RETURNS to
// the orchestrator; the human approves in chat before the next launches (resumeFromRunId
// caches finished work so nothing re-runs). Each phase below fans out to the §2.1 subagents.

// ========== SEGMENT A — Baseline → Boot & Verify  (halts at CP1) ==========
const booted = []
for (let i = 0; i < USE_CASES.length; i += BATCH) {
  const batch = USE_CASES.slice(i, i + BATCH)
  const res = await pipeline(batch,
    uc => agent(`Build baseline ${uc.name} (${uc.stack}, RBAC). No CometChat. Confirm it compiles,
                 commit locally on main. Return build exit code, commit SHA, output tail.`,
          {label:`baseline:${uc.name}`, phase:'Baseline', schema: BASELINE_SCHEMA}),
    (base, uc) => {
      if (!GATE.baseline(base)) throw new Error(`gate-fail:baseline:${uc.name}`)
      return agent(`Bring the ENTIRE ${uc.name} system up (docker compose for web+backend; Android
                    emulator + iOS simulator against the Dockerized backend). Health-check every
                    service, migrate/seed, run the baseline login smoke. DO NOT integrate anything.`,
             {label:`boot:${uc.name}`, phase:'Boot', schema: BOOT_SCHEMA})
    })
  booted.push(...res.map((boot, k) => ({ uc: batch[k], boot })))
}
// 🛑 CP1 — RETURN TO HUMAN. Review each baseline's boot evidence + login smoke + screenshots.
//    Provisioning + integration do NOT start until you approve. (resume launches Segment B.)

// ---- one-time app provisioning, AFTER the first baseline is confirmed up (post-CP1) ----
await agent(`Using the CometChat automation keys, create/configure the ONE shared app: enable Calls +
             moderation + reactions, set the webhook URL, register push keys. Emit cometchat-app-config.json.`,
      {label:'provision-app', phase:'Provision', schema: APP_CONFIG_SCHEMA})

// ========== SEGMENT B — Integrate → Re-Boot & Verify  (halts at CP2) ==========
const passed = booted.filter(x => GATE.baselineUp(x.boot))   // dead baselines drop out, tagged `agent`
const runs = []
for (let i = 0; i < passed.length; i += BATCH) {
  runs.push(...await pipeline(passed.slice(i, i + BATCH),
    ({ uc }) => {
      if (budget.total && budget.remaining() < 60_000) throw new Error(`budget-cut:${uc.name}`)
      return agent(`On branch cometchat-integration, integrate CometChat via pinned skills + docs-mcp
                    into web + Android + iOS + backend. Commit locally. Return telemetry.`,
             {label:`integrate:${uc.name}`, phase:'Integrate', schema: RUN_SCHEMA})
    },
    (run, { uc }) => {
      if (!GATE.integrate(run)) throw new Error(`gate-fail:integrate:${uc.name}`)
      return agent(`STEP 1 — Re-boot the INTEGRATED ${uc.name} system; confirm every service is
                    healthy AND the CometChat SDK inits with no error (integratedUp/sdkInitOk). If it
                    won't boot, STOP — that's a skills-tagged blocker; do not test calls.
                    STEP 2 — seed ~4-6 CometChat users, every UID/GUID prefixed with UC_SLUG
                    (mkt-admin, mkt-ticket-1…); record cometchatUsersSeeded (no deletion — quota raised).
                    STEP 3 — run the fixed e2e (login→chat→call) on web+Android+iOS, correct & re-run
                    up to ${MAX_RETRIES}× (report retryCount), then adversarially REFUTE it works.
                    STEP 4 — docker compose down -v + prune to FREE DISK; set dockerCleanupDone/diskFreedMB.
                    Return the full verdict + score.`,
             {label:`verify:${uc.name}`, phase:'Verify', schema: VERDICT_SCHEMA})
    }))
}
// 🛑 CP2 — RETURN TO HUMAN. Review each integration's chat/call e2e + diff + verdict per platform.
//    Consolidation + push do NOT start until you approve. (resume launches Segment C.)

// ========== SEGMENT C — Consolidate (barrier) ==========
const consolidated = await agent(
  `Aggregate these ${runs.filter(Boolean).length} runs plus the existing Deskline/Telehealth/Edtech
   feedback docs. Dedupe issues by ISS-*/G-* id, rank by frequency×severity, list top fixes for
   cometchat-skills and docs-mcp, and collect everything that hit the needsAttention channel.`,
  {phase:'Consolidate', schema: CONSOLIDATED_SCHEMA})

return { booted, runs, consolidated }   // → human reviews branches → foreground push + PR
```

---

## 8. Observability

- **`/workflows`** — the always-live native tree (phases → labeled child agents → status/tokens). Source of truth during the run.
- **In-chat dashboard widget** — the orchestrator re-renders the rich dashboard on a cadence (via `/loop`, ~30–60s or per phase transition) reading the workflow's live telemetry. Shows scores, retries, needsAttention, and the `ISS-*`/`G-*` rollup.
- **`log()` signals** — every gate-fail / retries-exhausted / hallucination emits a narrator line.
- **Completion** — a task-notification fires; the orchestrator relays the consolidated report + needsAttention list.

---

## 9. Re-run per release (Deliverable 4, automated)

Wrap the sweep in a **scheduled cloud routine** (`schedule` skill). On a new skills release: bump `skills-lock.json` hashes → re-run on fresh `cometchat-integration-vNEXT` branches → the aggregator **diffs** the new consolidated report against the previous ("ISS-1 fixed, ISS-9 new") — the measurable-improvement-per-iteration the objective asks for.

---

## 10. Cowork session setup (environment access)

Codegen/orchestration runs fine in cowork, but **Boot / Re-Boot / E2E need Docker + Android emulators + iOS simulators, which a cloud sandbox does NOT provide.** So run the cowork session **on (or connected to) the local machines** that have these toolchains.

### 10.1 Where cowork must run
- **Mac mini** — Xcode + iOS Simulator + Android Studio + Docker → can run *all* platforms; **required for every iOS slice.**
- **HP laptop** — Android Studio + Docker → web + Android slices.
- Run cowork **locally on these machines** (or a self-hosted/connected runner), **not the pure cloud sandbox**, so agents can `docker compose up`, boot AVDs, and drive simulators.

### 10.2 Access checklist (grant before launching)
| Access | For | How |
|---|---|---|
| **GitHub** | create repos, branch, commit *(push stays human)* | GitHub connector / `gh auth login` on the machine |
| **Docker** | boot/reboot/e2e of web+backend | Docker Desktop running; agent can run `docker compose` |
| **Android Studio + SDK + AVD** | Android build + emulator boot | Android Studio installed, ≥1 AVD created; `adb`, `emulator`, Gradle on PATH |
| **Xcode + iOS Simulator** *(Mac only)* | iOS build + simulator boot | Xcode + CLI tools; `xcodebuild`, `xcrun simctl`; a booted simulator |
| **CometChat automation keys** | `provision-app` (Phase 2.5) | in `.env.pipeline` |
| **docs-mcp** | the thing under test | connected in the cowork session's MCP config |
| Node / Python / Go / PHP / Java toolchains | per-stack builds | installed on the machine |

### 10.3 Cloud-OK vs local-only
- **Cloud OK:** codegen (requirements/design/research/integrate agents), consolidation, report generation, scheduled per-release re-runs that *skip* emulator phases (e.g. static-analysis re-checks).
- **Local only:** everything in Boot / Re-Boot / E2E — Docker + emulators + simulators can't run in the cloud sandbox.
- **Practical split:** full pipeline runs locally on Mac mini + HP; cowork cloud handles the async orchestration layer + scheduled re-runs.

### 10.4 Checkpoints in a cowork session
CP1 (after Boot) and CP2 (after Re-Boot & Verify) surface as the workflow returning a review packet in the session; you approve in chat and `resume` launches the next segment.

---

## Deliverables mapping
- **D1** baseline repos + integration branches + PRs → per use case (push human-gated)
- **D2** per-run feedback → `COMETCHAT_SKILLS_FEEDBACK.md` per repo (Run 01 = Deskline)
- **D3** consolidated report → Consolidate phase output, published as an Artifact
- **D4** the reusable pipeline → this doc + the Workflow script + the scheduled routine
