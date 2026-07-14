# STEP4 Pipeline — exact steps + reliability review

Two parts: **(1)** the precise step-by-step of what the pipeline runs, and **(2)** the genuine
structural issues observed during the reliability-revamp run (com), with root cause + fix direction.

---

## Part 1 — Exact step-by-step (what each stage actually does)

Driver: `batch_runner.py` runs **waves** (pairs of use cases) through ordered **segments** with human
**checkpoints**. Each segment step shells out to `run_usecase.py --use-case <slug> --stage <stage>`.
Every stage writes its result to `pipeline-state/<slug>/<stage>.json` (`state.write`) and emits
observability events — so a stage is individually re-runnable.

**Deterministic component expansion** (`prompts.expand_components`): archetype → fixed component list.
`N`=backend+web+android+ios · `R`=backend+web+mobile · `F`=backend+web+app. No LLM decides what runs.

| # | Stage | What it does (exactly) | Gate that must pass | Artifacts |
|--|-------|------------------------|---------------------|-----------|
| 0 | **provision-app** | Once per use case: `claude -p` creates a dedicated CometChat app `step4-<slug>`, writes creds to `runs/<slug>/.env.cometchat` (git-ignored) | app id present | `.env.cometchat`, `cometchat-app-config.json` |
| 1 | **preflight** | Expand components; `readiness.check` = are the **toolchains** for each stack installed (node/flutter/adb/xcodebuild/php/…) + docker; generate the spec-pin `requirements/<slug>.md` via `claude -p` if missing | `readiness.ready` (all toolchains present) | spec-pin |
| 2 | **build** | For **each component**, `claude -p` writes the BASELINE app (no CometChat); `verify.build_gate` compiles it; on a known compile-fail signature `selfheal.heal` repairs + retries once; commit "baseline" to `main` | `gates.baseline` (compiles + commit sha) | baseline code on `main` |
| 3 | **containerize** | `claude -p` writes Dockerfiles + root `docker-compose.yml`; commit | `gates.containerize` (compose file exists) | compose + Dockerfiles |
| 4 | **boot** | `docker compose up` the baseline; health-check services; login-smoke (page-200 / API) | `gates.baseline_up` (dockerUp ∧ allServicesHealthy ∧ loginSmokePassed) | boot state |
| 5 | **demo** | Boot-2: rebuild Android/iOS from the branch; gate that the mobile build **compiles** (media/interaction NOT exercised) | mobile build compiles | installed apps |
| — | **CHECKPOINT 1** | **Human** verifies web+Android+iOS are up (`--auto-approve` skips). Then `teardown` closes the demo | manual | — |
| 6 | **push-main** | Push the baseline `main` branch (auto-push on CP1 approval) | — | remote `main` |
| 7 | **integrate** | `git reset --hard main`; for **each component** `claude -p` adds CometChat; `build_gate` + `selfheal`; a concurrent **skills-critic** `claude -p` adversarially reviews each component; commit ONLY if every component compiles AND none was truncated | `gates.integrate` (compiles ∧ no truncation) | integration on `feature/cometchat-integration` |
| 8 | **verify** | Boot the integrated system; per-stack **runtime proof**: web e2e chat (`run_e2e`/`run_twoparty_web`), Flutter mobile chat-**receive** (`run_flutter_chat_receive_mobile`, vision-verified) | `gates.verify` (integrated boots ∧ chat proven) | verify state + shots |
| 9 | **demo** | Boot-2 again for the integrated branch → **CHECKPOINT 2** (human verifies integrated) | manual | — |
| 10 | **readme** | `claude -p` reads the repo and writes/commits root `README.md` on the feature branch | non-fatal | README |
| 11 | **push-branch** | Push `feature/cometchat-integration` (auto-push on CP2 approval) | `gates.verify` upstream | remote feature branch |
| 12 | **teardown** | FINAL: `docker compose down -v`, uninstall apps, shut sims/emulator | — | clean machine |

**Self-heal scope** (`selfheal.RULES`) — the *only* failures auto-recovered, all **build/config**:
`cleartext-http`, `jdk17`, `call-permissions`, `ios-deploy-target`, `gradle-stale`, `pod-modular`,
`disk-full`, `compose-env`, `cometchat-creds`. Each firing also records a witness finding.

**Failure attribution:** genuine CometChat skill/SDK/docs gaps → `pipeline-state/gaps/<slug>.md`
(rolled into `MASTER_GAPS.md`); harness/agent bugs → `pipeline-notes/<slug>.md`.

---

## Part 2 — Genuine issues from the revamp run (grounded in this session)

### A. The gates verify *compile + boot*, not *behavior* — so runtime bugs pass green, then break in manual testing
The whole gate chain (`baseline` → `baseline_up` → `integrate` → `verify`) proves the code **compiles**,
the stack **boots**, and **one chat message is received**. It does **not** exercise interactive/behavioral
features: **voice/video calling, role/permission flows (admin vs member), new-chat, session switching**.
`stage_demo` even gates mobile only on the build **compiling**, and calling is explicitly documented as
un-verifiable on emulators. Result this session: integrate/verify went GREEN while calling was a silent
no-op, admin couldn't connect, call buttons rendered twice, "user not found" for un-provisioned users —
**all found by hand, none by a gate.** This is the core of *"the pipeline broke when bugs started
occurring in the app."* The automation has no behavioral oracle for the features the app is built around.

**Fix direction:** add a **behavioral verify tier** — scripted interaction flows per feature (a two-device
call-connect assertion via the server `call.answered` event; a per-role login→chat matrix; a new-chat
create-conversation assertion) that run in `verify` and gate. Where a feature genuinely can't be verified
in-harness (real-device calls), the pipeline must **record an explicit "unverified" status**, not green.

### B. Test harnesses are stack-specific and hand-built mid-run — readiness only checks toolchains
`readiness.check` confirms the **compiler/SDK** is installed (`STACK_TOOLS`/`KIND_EXTRA`) — but the actual
**verify harnesses** (Maestro mobile flows, the flutter-semantics web driver, the two-party call matrix,
chat-receive) are bespoke code in `verify.py`/`e2e/` that gets **discovered-missing and written on the
fly** when a wave hits a stack whose harness isn't complete. That is exactly the inefficiency you felt:
the run stalls to build the harness for that stack. There is no "**harness registry + readiness gate**"
guaranteeing every stack in the 10-use-case matrix has a complete, self-tested verify harness *before*
the wave starts.

**Fix direction:** promote test harnesses to first-class, pre-provisioned assets: a `harness_readiness`
check in **preflight** that fails fast if the stack's verify harness is absent/stale, and a one-time
"build+self-test all harnesses" step so no wave ever authors a harness mid-flight.

### C. No deterministic recovery from a halt → the automation degrades into a chat
`selfheal` only knows a fixed set of **build** signatures. Any **novel** failure — a runtime bug, an
un-encoded build signature, a gate that trips for a new reason — makes `run_segment` print *"halted …
Fix + re-run this stage"* and **return**; the wave stops. The fix itself is not automated, and crucially
the **debugging context is not captured in resumable state** — it lives only in the conversation. So from
the first hand-fix onward, the remaining pipeline runs as prompt-driven conversation, which (as you said)
defeats the point of an automation. State is persisted per stage, but *why it failed and what was tried*
is not, so a fresh process cannot resume the debugging.

**Fix direction:** on any halt, emit a **structured resume packet** (failing stage, gate output, repo
diff, last N log lines, hypotheses) to `pipeline-state/<slug>/HALT.json`, and add a bounded
**diagnose→patch→re-gate loop** (an agent that proposes a fix, applies it in an isolated worktree,
re-runs only the failed gate, and either lands it or escalates with the packet). That keeps recovery
inside the automation and makes a halt resumable by a fresh run, not a conversation.

### D. No canonical step-by-step spec (fixed by Part 1 of this doc)
`RELIABILITY_REVAMP.md` is a *what-changed* changelog; there was no single doc stating each stage's exact
inputs → actions → gate → outputs. Part 1 above is that spec; keep it in sync with `STAGES`.

---

### One-line root cause
The pipeline is a strong **build-and-boot** automation with a weak **behavioral-verify** and **failure-recovery**
layer. It reliably produces something that *compiles and starts*; it does not yet reliably prove the app
*behaves*, nor recover *itself* when a novel bug appears — which is why every real app bug this session
bounced out to manual debugging.
