# STEP4 Pipeline — Resilience & Continuity Implementation Plan

Goal: make a wave **run to completion serially and unattended** — never bouncing out to manual
conversational debugging, never losing context on a halt. This is the intended **last** structural
change: after it, the remaining use cases should run smoothly.

---

## 0. The one reframe that makes this robust

Your proposal — *"run the pipeline as an alive background process with a memory layer, a separate agent
runs it, you relay to me"* — is the right shape. One correction that turns it from fragile to bulletproof:

> **Don't keep a process "alive the whole time." Make it durable and resumable.**

A long-lived in-memory process is the *fragile* pattern: one crash, OOM, or laptop sleep loses everything,
and there's no watchdog. The industry-proven answer is **durable execution** — persist every completed
step to a journal; on any interruption a *fresh* process replays the journal and resumes from the last
completed step, not from zero ([DBOS](https://www.dbos.dev/blog/durable-execution-crashproof-ai-agents),
[Inngest](https://www.inngest.com/blog/durable-execution-key-to-harnessing-ai-agents)). Critically,
naive checkpointing is **not** durable execution — it saves state but has "no supervisor, no watchdog, no
heartbeat," no automatic recovery, and no exactly-once guarantee for side effects like git pushes or docker
([Diagrid](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows)).
So "alive without losing context" = **durable journal + memory layer + a supervisor that owns the lifecycle**,
not a process that never stops.

Anthropic's own long-running-agent guidance says exactly this: an **initializer** sets up memory files, then
an **incremental-progress agent** reads them, does one unit of work, verifies it end-to-end, updates the
progress log, and exits — repeat until done ([Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), [cwc-long-running-agents](https://github.com/anthropics/cwc-long-running-agents)).

---

## 1. Target architecture — three separated layers

```
┌─ COMMUNICATION AGENT (me / a Claude Code session) ── human-facing only ─┐
│   relays status, asks for the 2 human checkpoints, takes directives.     │
│   Owns NO execution state. Reads the journal + memory to answer.         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ (start / resume / status)
┌─ SUPERVISOR (durable driver) ▼ owns the wave lifecycle ─────────────────┐
│   Runs stages serially. After each step → append to JOURNAL.             │
│   On failure → DIAGNOSE→PATCH→RE-GATE loop (bounded). Escalate only if    │
│   the loop is exhausted, with a full HALT packet. Watchdog/heartbeat.     │
└───────┬───────────────────────────────┬─────────────────────────────────┘
        │ execution state                │ semantic/debug context
┌───────▼─────────────┐        ┌─────────▼────────────────────────────────┐
│ DURABLE JOURNAL      │        │ MEMORY LAYER (markdown, source of truth)  │
│ which stage/step is  │        │ what failed & why, fixes tried, per-UC    │
│ done; idempotency    │        │ knowledge, the gaps ledger. Injected at    │
│ keys; resume cursor  │        │ the start of every supervisor session.     │
│ (extends state.write)│        │ (Anthropic memory tool `/memories/…`)      │
└─────────────────────┘        └────────────────────────────────────────────┘
```

Two durability concerns, kept separate (this is the key design decision):
- **Execution durability** ("which stage is done, don't repeat side effects") → the **journal**.
- **Context durability** ("why did calling fail, what did we already try") → the **memory layer**.
The pipeline already has the seed of the journal: `state.write(S, slug, stage, result)` per stage. We
harden that into a real journal and add the missing supervisor + memory + recovery loop around it.

---

## 2. How this fixes the three issues from the review

| Issue (from PIPELINE_GUIDE Part 2) | Mechanism in this plan |
|---|---|
| **A. Runtime bugs pass green, break in manual test** | A **behavioral-verify tier** in `verify`: scripted per-feature assertions (two-device call-connect via server `call.answered`; per-role login→chat matrix; new-chat creates-conversation). A feature that can't be verified in-harness records an explicit **`unverified`** status in the journal — never silent green. |
| **B. Test harnesses hand-built mid-run** | A **harness registry** + a `harness_readiness` gate in `preflight` that fails fast if the stack's verify harness is absent/stale, and a one-time "build+self-test all harnesses" bootstrap so no wave ever authors a harness mid-flight. |
| **C. Halt → automation degrades to chat** | The **supervisor** owns the lifecycle: on failure it writes a **`HALT.json` resume packet** (failing stage, gate output, repo diff, last-N logs, hypotheses) + a memory entry, runs a **bounded diagnose→patch→re-gate loop** in an isolated git worktree, and only escalates to the human if the loop is exhausted. Recovery stays *inside* the automation; a fresh supervisor session resumes from the journal + memory, not the conversation. |
| **D. No step spec** | Fixed — see `PIPELINE_GUIDE.md` Part 1. |

---

## 3. Control plane — steering a running pipeline

You never edit state directly — you talk to the communication agent (me), which controls the running
pipeline on your behalf. The supervisor is steerable **because** state lives in the journal + memory, not
a locked process: a directive is an instruction read at the next safe boundary, then a controlled
re-entry — not the interruption of a fragile process.

**Flow:** you → me (plain language) → I classify + confirm scope → a structured entry in the **command
inbox** (`COMMANDS.jsonl`) + a memory note → the supervisor reads the inbox at **safe boundaries**
(between steps, never mid-side-effect) and re-enters at the right point. This is the durable-execution
"signal" mechanism (Temporal signals / DBOS `send`+`recv`).

**Severity → re-entry point:**
- **Tweak** (flag/env/constraint) → applied at the next step; nothing redone.
- **Redirect a stage** (change a component's stack/spec) → update spec-pin + memory; re-run **from that
  stage only**, downstream replays from the journal.
- **Drastic** ("approach is wrong") → rewind to a journaled checkpoint and re-plan — a controlled rewind,
  not from-scratch.
- **Override the auto-fix loop** → halt the loop before it lands (fixes land in an isolated worktree +
  re-gate first, so nothing is committed until it passes).
- **Hard stop** → soft-interrupt flag: finish the current atomic step, then pause and wait.

**Autonomy levels** (change any time): **auto** (auto-fix + continue) · **gated** (pause per stage) ·
**checkpoint-only** (today's CP1/CP2). An **interrupt** ("pause") is always honored at the next boundary.

## 4. Command scope — global vs per-use-case (so the journal never mixes them)

Two command scopes, two **physically separate** stores. The **journal stays per-UC** (that UC's execution
state + its own directives); **global policy lives outside it and is referenced, not copied.**

- **Per-UC** → `pipeline-state/<slug>/{COMMANDS.jsonl, DIRECTIVES.md}` — only that UC's supervisor reads it.
- **Global** → `pipeline-state/global/{COMMANDS.jsonl, POLICY.md}` — every UC's supervisor reads it at
  startup + each boundary. A global command is stored **once**; when it triggers a re-run in `com`, com's
  journal records a *reference* (`caused_by: G-007`), not a copy → single source of truth, no drift.

**Scope is pinned at capture, not at read.** When you give a command I classify + **confirm** it
(*"com only, or a global default for every use case?"*) before writing, so every entry carries
`scope: "usecase:com"` or `scope: "global"`. The journal never guesses.

**Precedence** (layered like CLAUDE.md global + project memory): **policy / constitution** = a hard floor a
per-UC directive cannot override (secrets, verify-required); **defaults** = per-UC may override (e.g. the
default backend). Effective rules = GLOBAL ⊕ per-UC.

**Reach:** because each UC reads `global/POLICY.md` at its own preflight/build, a global directive flows
into the spec-pin + codegen prompts of every UC that runs **after** it — including ones not built yet.
Re-applying a global change to **already-finished** UCs is opt-in (I confirm before scheduling fan-out
re-runs; each rewinds to its own checkpoint).

**Provenance:** every journal re-entry is tagged with the causing command's id + scope, so *"why did com
rebuild?"* always resolves to a specific directive — nothing is ambiguous because scope was pinned before
it was written.

## 5. Implementation options + tradeoffs

Five ways to get the durable core. Ordered lightest → heaviest.

| # | Option | What it is | Pros | Cons / risk |
|--|--------|-----------|------|-------------|
| 1 | **Extend the existing Python journal + a supervisor loop** | Harden `state.write` into an append-only journal (idempotency keys, resume cursor); add a supervisor driver replacing `batch_runner`'s "halt & return" with a recovery loop + watchdog. | No new deps/infra; builds on what exists; you fully own it; fastest to ship. | You hand-roll durability — the "checkpoints ≠ durable execution" trap (exactly-once side effects, concurrent-resume coordination) is easy to get subtly wrong. |
| 2 | **DBOS (in-process durable execution)** | Wrap stages as `@DBOS.workflow()`/`@DBOS.step()`; checkpoints to Postgres/SQLite; auto-resumes from last completed step. | *Real* durable-execution guarantees (exactly-once, transparent auto-recovery) with **minimal infra — a library + a DB, in-process** ([DBOS](https://pydantic.dev/articles/pydantic-ai-dbos)). Best durability-per-effort. | Rewrite stages into workflow/step functions; adds a Postgres/SQLite dependency; steps must be idempotent. |
| 3 | **Claude Agent SDK long-running harness + memory tool** (⭐ matches your vision) | The supervisor IS an Agent SDK session (`resume=session_id`, `fork_session`), delegating to **subagents** (build/verify/diagnose workers); the **memory tool** (`memory_20250818`, GA) holds context in `/memories/…`; **context editing** (`clear_tool_uses_20250919`) keeps the long loop in-window; **hooks** (`PostToolUse`, `SubagentStop`) checkpoint to the journal. | Purpose-built for exactly this; **is** your "separate agent runs the pipeline + memory layer + I relay" design; session resume + subagent orchestration + JIT memory are first-class ([Agent SDK sessions](https://code.claude.com/docs/en/agent-sdk/sessions), [memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool), [context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)). | Newer; Agent SDK usage draws a separate credit; **execution**-durability (exactly-once side effects) is weaker than DBOS/Temporal — needs disciplined idempotency for git/docker/provisioning. |
| 4 | **Managed Agents** (Anthropic-hosted) | Hosted sessions with a durable server-side event log + sandbox; resume by posting new events. | Zero infra; durable server-side; multi-agent built in. | Beta; Anthropic stores session state (no ZDR/HIPAA); least control; cost. |
| 5 | **Temporal** (full durable engine) | Stages become Temporal activities/workflows on a Temporal server. | Gold-standard durability, distributed, battle-tested, sleeps for days then wakes ([Temporal](https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal)). | Heavy infra (Temporal server + workers); biggest rewrite; overkill for a locally-run pipeline. |

### Recommended: **hybrid of #3 (orchestration/context/comms) over #1-or-#2 (execution journal)**
Separate the two durability concerns and use the right tool for each:
- **Orchestration + memory + communication → Agent SDK harness (#3).** It literally is your proposed
  design and Anthropic's long-running-agent pattern: a durable supervisor session + the memory tool +
  subagent workers + a thin communicator. This is where the "no lost context, no manual chat" win comes from.
- **Execution journal → start with #1, graduate to #2 (DBOS) only if side-effect exactly-once bites.**
  For a locally-run pipeline, a hardened append-only journal with idempotency keys (option 1) is enough and
  ships fast. Adopt DBOS (option 2) if/when duplicate git pushes, double provisioning, or concurrent-resume
  races actually appear — its in-process model means that upgrade is contained.
- **Skip #4/#5** unless this becomes a hosted multi-tenant service (they're right for that, overkill here).

Why not "just keep it alive" (your literal phrasing): see §0 — a live process has no recovery story; the
hybrid gives the *same* felt experience ("it just keeps going, remembers everything") with real crash-safety.

---

## 6. Concrete build (phased — each phase is independently valuable)

**Phase 1 — Journal + supervisor + HALT packet + control plane (fixes Issue C, the highest-leverage).**
- Harden `state.write` → append-only `pipeline-state/<slug>/journal.jsonl` with `{stage, step, status, idempotencyKey, sha, caused_by, ts}`; add a `resume_cursor`.
- New `supervisor.py` replacing `batch_runner`'s halt-and-return: runs the segment sequence, and on a gate
  fail writes `HALT.json` (stage, gate output, `git diff`, last-N `_logs`, hypotheses) and enters the
  recovery loop below. Heartbeat file so a watchdog/communicator can tell "running" vs "stuck".
- **Control plane from day one (§3–§4), not bolted on later:** the command inbox — per-UC
  `pipeline-state/<slug>/COMMANDS.jsonl` **and** global `pipeline-state/global/COMMANDS.jsonl` — read at
  every safe boundary; the two-tier scope stores (`global/POLICY.md` + `<slug>/DIRECTIVES.md`) with the
  precedence + `caused_by` provenance rules. The supervisor's boundary check = "apply pending commands
  (global ⊕ per-UC), then proceed."
- Idempotency: every side-effecting stage (push, provision, docker) checks the journal before acting →
  safe to resume.

**Phase 2 — Diagnose→patch→re-gate loop (fixes Issue C fully).**
- A `diagnose` worker subagent: given the HALT packet, proposes a fix, applies it in an **isolated git
  worktree**, re-runs **only the failed gate**. If green → land + journal it; if not, up to N attempts then
  escalate to the communicator with the packet. This generalizes `selfheal` from a fixed signature list to
  novel bugs, while keeping the witness/gaps discipline.

**Phase 3 — Memory layer (context durability).**
- Adopt the memory tool (`BetaLocalFilesystemMemoryTool`) rooted at `pipeline-state/memory/`: a per-UC
  `PROGRESS.md` (what's done / next), `LEARNINGS.md` (root-caused bugs + fixes, e.g. the avatar:null and
  async-getLoggedInUser findings), and the existing gaps ledger. Injected at the start of every supervisor
  session so a resume has full context. Enable context editing on the supervisor loop.

**Phase 4 — Behavioral-verify tier (fixes Issue A).**
- Add scripted per-feature assertions to `verify` (call-connect, per-role matrix, new-chat) that gate;
  features that can't be verified in-harness write `status: unverified` to the journal (never green).

**Phase 5 — Harness readiness (fixes Issue B).**
- A harness registry (`e2e/harnesses/<stack>/`) + a `harness_readiness` check in `preflight` that fails
  fast if a stack's verify harness is missing/stale; a one-time bootstrap builds + self-tests all of them.

**Phase 6 — Communicator split.**
- The human-facing agent (me) reads journal + `HALT.json` + heartbeat to report status and relay the 2
  human checkpoints; it holds no execution state, so the supervisor can crash/resume under it transparently.

---

## 7. Risks & mitigations
- **Exactly-once side effects** (double push/provision) → idempotency keys in the journal (Phase 1); DBOS if it bites.
- **Auto-fix loop landing a wrong fix** → isolated worktree + re-gate before landing + bounded attempts + witness/gaps logging so a bad fix is visible, never silent.
- **Behavioral verify still can't cover real-device calls** → explicit `unverified` status is the honest floor; don't fake green.
- **Agent SDK credit cost / newness** → the execution journal (#1/#2) is framework-agnostic, so the durable core survives even if the Agent SDK layer is swapped.

---

## Sources
- Anthropic — [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) · [cwc-long-running-agents](https://github.com/anthropics/cwc-long-running-agents)
- Anthropic — [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) · [Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) · [Agent SDK sessions](https://code.claude.com/docs/en/agent-sdk/sessions) · [subagents](https://code.claude.com/docs/en/agent-sdk/subagents) · [hooks](https://code.claude.com/docs/en/agent-sdk/hooks) · [Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview)
- Durable execution — [DBOS: crashproof AI agents](https://www.dbos.dev/blog/durable-execution-crashproof-ai-agents) · [Pydantic AI + DBOS](https://pydantic.dev/articles/pydantic-ai-dbos) · [Diagrid: checkpoints are not durable execution](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows) · [Inngest](https://www.inngest.com/blog/durable-execution-key-to-harnessing-ai-agents) · [Temporal + Pydantic AI](https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal)
- Memory layer — [State of AI agent memory 2026 (mem0)](https://mem0.ai/blog/state-of-ai-agent-memory-2026) · [Markdown-based agent memory (DEV)](https://dev.to/imaginex/ai-agent-memory-management-when-markdown-files-are-all-you-need-5ekk)
