# STEP4 Hybrid Pipeline

Deterministic Python **plumbing** + `claude -p` **codegen** + a Python-encoded **gate contract**.
Combines the token-efficiency & robustness of a scripted worker with the quality guards of the
agent-native design.

## The split (why it's cheap + robust)
- **Deterministic (zero-token):** control flow, component expansion, git/branch handling, `gh` repo
  create + push, docker/native build gates, boot/health checks, prompt rendering, gaps aggregation.
- **LLM (paid, only where judgment is needed):** per-component code generation (`build`/`integrate`)
  and a Claude-vision screenshot judge (visual-only checks). The pass/fail VERDICT is deterministic —
  no LLM adjudicates "did it work". Nothing else spends tokens.

## Two layers
- `run_usecase.py` — **stateless worker**: one stage per invocation, exits after each. All state on
  disk (git repo in `runs/<slug>/`, JSON in `_reports/` + `pipeline-state/`). Re-run a stage to recover.
  **Never blocks on input()** — safe to call headless from Bash.
- **Conductor** — sequences stages and holds the 2 human checkpoints. Either a Claude session
  (AskUserQuestion gates) or `batch_runner.py` (typed `go` gates, for running outside a session).

## Stages & gates
```
build ─► boot ─🛑CP1─► push-main ─► integrate ─► verify ─🛑CP2─► push-branch
  │        │                          │            │
 GATE.     GATE.                      GATE.        GATE.
 baseline  baselineUp                 integrate    verify (integratedUp ∧ ¬refuted)
 (agent)   (agent, false-pos guard)   (skills)     (skills)
```
- Phase A (`build`) omits skills + docs-mcp (clean baseline). Phase B (`integrate`) adds them.
- A gate fail exits non-zero → conductor halts (never advances on red). Tag: `agent` for a dead
  baseline, `skills` for a modified system that won't boot / SDK-init fails.
- `verify` computes a **deterministic scorecard** of cross-party machine evidence — a second party
  actually RECEIVES a unique message (live socket), a two-party call is logged answered server-side,
  and the CometChat SDK genuinely initialised. `refuted = not(sdkInit ∧ chatReceive ∧ callConnect)`;
  a Claude-vision FAIL on a call-critical rubric also refutes (`verify.vision_gate`). No LLM judge.

## Run it
```bash
# single stage (headless worker)
python3 run_usecase.py --use-case mkt --stage build

# full wave-of-2 with typed checkpoints (outside a session)
python3 batch_runner.py --wave 0

# roll up results
python3 aggregate.py          # -> pipeline-state/aggregate.{json,md} + refreshes MASTER_GAPS.md
```

## Config
- `config/use_cases.json` — the 10-use-case matrix + wave plan.
- `config/settings.json` — models per stage, max-turns, paths, the **Phase A/B claude args seam**,
  and `verify.e2e` commands (empty = recorded `not-configured`, never a fake pass).
- `requirements/<slug>.md` — spec-pin each baseline (roles/entities/flows/API) for consistency.
- `prompts/*.tmpl` — build / integrate / judge prompt templates (string-substituted, no LLM).

## The one seam to confirm
`settings.phaseB_extra_args` + `link_skills_into_project` control **how skills + docs-mcp attach**
to the Phase B `claude -p` call. Verify the flag names against your installed Claude Code version
(this is the exact thing the other pipeline flagged in `lib/claude_runner.py`). Everything else is
version-independent.
