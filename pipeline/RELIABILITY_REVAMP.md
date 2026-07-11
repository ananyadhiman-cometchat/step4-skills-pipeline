# Reliability revamp — what changed and why

This branch (`pipeline/reliability-revamp`) rebuilds the pipeline's **verification layer** so "green"
means "actually works." The architecture is unchanged (deterministic Python plumbing + `claude -p`
only where judgment is needed) — the fix is the *trustworthiness of the signals*. No new frameworks.

## The one-line problem it fixes
The eval verdict used to be `refuted = not (chat_ok and call_ok)` where `call_ok` = "a call-shaped DOM
element exists" and `chat_ok` = "the word *camera* is on screen + the sender's own echo." Neither needs
a working socket, so a broken integration (or one where Claude stopped midway but the file still
compiled) reported **success**. The verdict is now a **deterministic scorecard of cross-party machine
evidence**.

## What changed (by theme)

### Stop the false-greens
- **Truncation gate.** `claude -p` outcomes now carry `agentOk` (exit 0 ∧ not `is_error` ∧ not
  `max_turns`); `GATE.baseline`/`GATE.integrate` fail when any component was truncated/errored — even
  if it compiles. Envelope parsing is robust (scan for the result object; capture `is_error`/`subtype`/
  `num_turns`/`cost`/`session`). `claude_runner.py`, `gates.py`.
- **Cross-party receive proof** (`e2e/twoparty_chat.web.mjs` + `verify.run_twoparty_chat`): B sends a
  unique per-run nonce, **A must render it over a live socket**. This is the source of truth for chat
  and catches "socket dead but REST login works."
- **Real call proof:** `call_ok` = the two-party matrix (signaling + server-answered), with
  `call_answered` reading the log as the **actual** call-test uid (was hardcoded `{slug}-buy-001`, a
  no-op for every non-mkt use case). The single-browser call verdict no longer matches the call *button*.
- **Real SDK-init:** `sdkInitOk` requires the kit's conversation list to render — dropped the
  `or app-login` fallback (app login proves nothing about CometChat).
- **Real build gates:** Node backend type-checks (not just `npm install`); RN no longer passes on a
  `lint` script; the `node_modules` type-error relaxation only applies when the failure genuinely is a
  library-types issue; `flutter analyze` is non-fatal on infos/warnings. `verify.py`.
- **Mobile in the verdict:** an integrated mobile client that built+launched but connected no call leg
  is recorded as `mobileRefuted` (hard-gates behind `verify.mobile_gate`). `run_usecase.stage_demo`.
- **Vision teeth:** a Claude-vision FAIL on a call-critical rubric refutes (`verify.vision_gate`).
- **No retry-until-pass:** the blind 6× loop is gone; one bounded, harness-aware retry that records
  every attempt.

### Correct failure attribution (stop poisoning the gaps ledger)
- One deterministic cause classifier (`obs.classify_cause`) → `infra | agent | harness | skills | setup`.
  Boot/health failures are `infra`, selector timeouts are `harness` — never mislabelled `skills`.
- `verify` fails as **infra** when the integrated system won't boot (health-checks backend **and** web).

### Recovery
- **Integrate rollback:** `git reset --hard main && git clean -fdq` before codegen, so a re-run never
  edits over a prior partial tree.
- **Self-heal parity:** the heal engine now runs in `integrate` too (was build-only), and the JDK17
  heal's env is actually threaded into the re-gate (it used to no-op).
- **Timeouts:** every `claude -p` has a hard wall-clock cap (`settings.stage_timeout_s`) — a wedged
  agent can't hang the conductor.
- Resume-state (`phase_status`) tracks all 11 stages; unknown wave slugs **fail loud** (was silent).

### Security
- **Pre-push secret scan** (`secrets.scan_repo`) blocks a push if any real secret VALUE appears in a
  tracked file — the promised-but-absent §4.6 gate. Runs before `push-main` and `push-branch`.
- **Env allowlist:** the integrate codegen agent no longer sees the automation/REST/webhook secrets.
- **Log redaction:** secret values are scrubbed from `_logs/*.log` and tails.
- `.dart_define.json` / `local.properties` (where self-heal writes real creds) are gitignored.

### Observability
- Per-run JSONL manifest + failure records under `runs/<slug>/_run/` (`obs.py`): run id, wave id,
  per-stage events, classified failure cause + evidence pointers. Cost/turns/session captured (were
  discarded).

### Deleted (unnecessary complexity)
- The perceptual visual-baseline layer (`visual_baseline.py`) — flagged CHANGED on every fake-media
  call frame, gated nothing.
- The dead LLM-judge scaffolding (`render_judge`, `_parse_judge`, `judge.md.tmpl`) + the docs that
  claimed it ran.

## Deferred (intentionally not in this branch)
- **Per-slug port offsets** for true concurrent lanes (needs the generated compose to read ports from
  env). Today: use cases still run sequentially on `:8080`/`:3000`; the compose builder-prune scoping
  and `-p <slug>` project naming are follow-ups.
- **Mobile cross-party chat-receive** via a Maestro flow (the web cross-party proof is in; mobile still
  relies on the call matrix + login→home vision).
- **Per-component memoization** (skip already-green components on re-run) — deliberately omitted to keep
  the integrate rollback deterministic; add behind a flag later.
- **Vision confidence/abstain** scoring (the gate teeth are wired; confidence is a refinement).

## How to validate
```bash
# static (no toolchain needed)
cd pipeline
python3 -m py_compile run_usecase.py batch_runner.py lib/*.py
for f in e2e/*.mjs; do node --check "$f"; done
# gate + classifier unit checks are in the commit message of the Tier-1/Tier-4 commits

# end-to-end (needs Docker + emulators + a provisioned app in .env.pipeline)
python3 run_usecase.py --use-case mkt --stage verify   # exercises the new cross-party verdict
```
End-to-end behavior (cross-party receive, two-party call, secret scan on push) can only be fully
confirmed on a real run with Docker + a provisioned CometChat app — the static + unit checks above
cover the deterministic logic.
