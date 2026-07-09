# Marketplace (mkt) — non-skills notes (codegen / harness / setup)

> These were found while building UC1 but are NOT CometChat skills/MCP-docs inconsistencies, so they
> are deliberately kept OUT of `pipeline-state/gaps/mkt.md`. Three buckets:
> (C) AI/codegen mistakes against a *correct* skill, (D) our pipeline/harness bugs, (E) operator setup.

## C — AI / codegen adherence misses (the skill was correct; the agent didn't follow it)
- **Android incoming call showed no accept/reject widget.** Codegen registered
  `CometChat.addCallListener` with an EMPTY `onIncomingCallReceived: () => {}` on a LEAF screen
  (ConversationThreadScreen) instead of the skill's root `CallSurfaces`. The `cometchat-native-calls`
  skill documents this exact bug (F75) and the correct root-mount pattern. Fixed by mounting
  IncomingCall/Outgoing/Ongoing at APP ROOT with both `CometChat.addCallListener` and
  `CometChatUIEventHandler.addCallListener`.
- **Mobile "blank on starting a call."** Codegen passed `callSettingsBuilder={CometChatCalls.CallSettingsBuilder}`
  (the CLASS). The skill's example is `new CometChatCalls.CallSettingsBuilder().setIsAudioOnlyCall(...)`
  (an INSTANCE). Class → component can't build settings → blank screen.
- **Duplicate call handling.** Codegen ran call handling on BOTH the leaf ConversationThreadScreen
  and the root, conflicting. The skill says mount call UI at ROOT only.

## D — Pipeline / harness bugs (ours, not CometChat's)
- **e2e `ERR_MODULE_NOT_FOUND: @playwright/test`.** Our `chatcall.web.mjs` ran from a dir where the
  package didn't resolve. Fixed by copying the script into `web/` before running. This had been
  mis-recorded as a "skills-blocker" in the gaps file because `stage_verify` auto-appended the raw
  failure — see the classifier fix below.
- **"integrated system SDK init failed"** — a vague auto-logged symptom of the compose-env gap
  (skills item #1); not a distinct finding.
- **Mobile creds not injected.** The pipeline's integrate stage wired CometChat code but didn't
  propagate real creds from `.env.pipeline` into `mobile/.env` → iOS baked the placeholder appId.
  Fixed with `mobile.write_cometchat_env()` (called before every integrated mobile build). The
  *SDK-should-fail-loud* half of this is a genuine skill/SDK ask and lives in gaps/mkt.md #5.
- **`stage_verify` recorded failures without classifying cause** → it dumped harness stack traces
  into the skills gaps file. FIXED: it now tags each recorded line by cause (skills vs harness vs
  setup) and only skills/SDK causes go to `gaps/`, the rest to this file.

## E — Operator / dashboard setup (not a defect)
- **AI moderation not enabled.** Probe (2026-07-09) sent profanity+PII buyer→seller; CometChat stored
  it unchanged. The Moderation / Data-Masking / Profanity extension is simply not toggled on in the
  dashboard for app 1680742d290138a01. Enable it, then verify's `check_moderation` reports
  `active:true`. Config state, not a code/skill gap.
- **Two-party call matrix** — coverage tracking for our own harness (web↔web, android↔web, ios↔web ×
  voice+video, all automated + passing via `twoparty.web.mjs` + `twoparty_mobile.py`). Not a gap;
  recorded for completeness.
