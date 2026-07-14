# Resilience layer — durable supervisor harness (hybrid Option 3)

Implements PIPELINE_RESILIENCE_PLAN.md: an Agent-SDK-style **supervisor** (the brain) on a durable
**journal** (the hands) + a **memory layer**, so a wave runs to completion unattended, survives halts,
and stays steerable. Additive — it wraps the existing `run_usecase.py` stages; nothing in the old
pipeline changed.

## Run it (the communicator drives these on your behalf)
```
supervisor.py run     --use-case com [--autonomy auto|gated|checkpoint]   # start / resume a use case
supervisor.py run     --wave 1                                            # a whole wave
supervisor.py status  --use-case com                                     # resume cursor, halt, inbox
supervisor.py command --scope global|usecase:com --kind <kind> [--target ..] [--body ..]
supervisor.py approve --use-case com                                     # clear a checkpoint pause
```
Re-running `run` after a crash / halt / pause **resumes from the journal** — it skips completed stages.

Command kinds: `pause` `resume` `abort` `autonomy` (target=auto|gated|checkpoint) `redirect` (target=stage)
`rewind` (target=stage) `override_fix` `tweak` (body) `note` (body).

## Files
| Path | Role |
|---|---|
| `supervisor.py` | durable driver: resume, command inbox, diagnose loop, autonomy, heartbeat |
| `lib/journal.py` | append-only journal (`journal.jsonl`), resume cursor, HALT packet, heartbeat |
| `lib/directives.py` | control plane + two-tier scope (global `POLICY.md` ⊕ per-UC `DIRECTIVES.md`) |
| `lib/memory.py` | `PROGRESS.md` + `LEARNINGS.md`; `session_context` injected into every worker |
| `lib/diagnose.py` | diagnose→patch→re-gate loop in an isolated worktree |
| `lib/behavioral.py` | behavioral-verify tier (records `unverified`, never fake-green) |
| `lib/harness.py` | harness-readiness registry (preflight fails fast if a verify harness is missing) |
| `pipeline-state/global/POLICY.md` | the constitution — hard floors + carried-forward CometChat defaults |
| `pipeline-state/<slug>/*` | per-run state (journal, heartbeat, HALT, PROGRESS, inbox) — git-ignored |

## Phase mapping (all six, from the plan)
1. **Journal + supervisor + HALT + control plane** — `journal.py`, `supervisor.py`, `directives.py`.
2. **Diagnose→patch→re-gate** — `diagnose.py`.
3. **Memory layer** — `memory.py` + `pipeline-state/global/LEARNINGS.md`.
4. **Behavioral-verify tier** — `behavioral.py` (verify stage publishes per-feature results; the rest is `unverified`).
5. **Harness readiness** — `harness.py`.
6. **Communicator split** — the supervisor holds no human-facing state; `status` + heartbeat + `HALT.json` are the relay surface.

## Notes / next
- Execution durability is the hand-rolled journal (Option 1) with idempotency on side-effecting stages.
  Graduate to DBOS (`@DBOS.workflow`/`@DBOS.step`) if a double-push/provision race ever appears — the
  supervisor is unchanged because the journal is framework-agnostic.
- Wire `verify` to publish `behavioral` results (`state.write(... "verify", {"behavioral": {...}})`) as
  the per-feature runners land; until then those features are honestly reported `unverified`.
