# MASTER_GAPS.md — live gaps ledger (MCP + skills)

> **Auto-generated** by `scripts/build-master-gaps.sh` — do not hand-edit; edits are overwritten.
> Regenerated: **2026-07-09 17:26:26 IST**. Source: `pipeline-state/gaps/<slug>.md` (one per use case, written by the integrate/verify agents as they run).

Two buckets, exactly the brief's metric families (§5.1 skill activation · §5.4 docs-mcp):

| Bucket | Tag markers agents emit | This run |
|---|---|--:|
| **docs-mcp** | `coverageGap:` (query returned nothing) · `staleness:` (doc vs SDK) · `docsEscape:` (left mcp to web-search/guess) | 0 / 0 / 0 |
| **skills** | `missedTrigger:` (no skill fired) · `falseTrigger:` (wrong skill) · `variant:` (v5/v6 mis-pick) · `hallucination:` (non-existent API) | 2 / 0 / 0 / 0 |

## Known / expected gaps (pre-seeded, verify during run)
- **`missedTrigger:` Vue has no `cometchat-vue` skill** → UC5 (Fintech) & UC10 (Event). Expect NO skill to fire on the Vue 3 web slice — **record it, don't treat as agent failure** (STEP4_PIPELINE §1). CometChat *ships* a Vue UI Kit, so this is the sharpest coverage gap.

---

## Per-use-case findings

# Marketplace (mkt) — CometChat skills & MCP-docs inconsistencies

> Scope: ONLY genuine gaps in the CometChat **skills** or **MCP docs** (and CometChat **SDK**
> packaging/behaviour) found while building UC1. AI/codegen mistakes against a *correct* skill,
> pipeline/harness bugs, and operator/dashboard setup are NOT here — see
> `pipeline-state/pipeline-notes/mkt.md`.

## MCP docs
- **none.** Every docs query during integration returned usable content — no coverage gap,
  staleness, or docs-escape recorded for UC1.

## Skills — docs/coverage gaps
Skills produced type-clean app-side code on all 3 components; these are places the skill guidance
was incomplete or missing:

1. **missedTrigger:** deployment env not wired. Integration wired `NEXT_PUBLIC_COMETCHAT_*` /
   `COMETCHAT_*` reads into code but only into `.env.example` — not into `docker-compose.yml`. The
   integrated system boots without CometChat creds and SDK init fails. *Skill ask:* the deployment
   step should inject creds into the actual runtime env (compose/service), not just the template.

2. **missedTrigger:** iOS Podfile `use_modular_headers!` missing. The Swift `react-native-cometchat-ui-kit`
   pod fails `pod install` because deps (SPTPersistentCache / DVAssetLoaderDelegate) don't define
   modules. *Skill ask:* add it via an `expo-build-properties` / config plugin so it survives
   `expo prebuild` (which regenerates the Podfile). We had to hand-add targeted modular headers.

3. **Web message-list does not scroll (recurring).** The CometChat UI Kit message list needs a
   bounded-height / `overflow` container; the skill's mount layout doesn't provide one, so the list
   grows unbounded and never scrolls. *Skill ask:* the mount recipe should ship the bounded-height
   wrapper (we used `.cc-msg-list { flex:1 1 0; min-height:0; height:100%; overflow:hidden }` plus a
   child rule for the kit's auto-injected `.cometchat` element).

4. **F-web-call — prebuilt call components have no positioning for Standard mode.**
   `cometchat-react-calls` mounts `<CometChatIncomingCall />` / `<CometChatOutgoingCall />` at root
   but gives fixed/inset overlay guidance ONLY for the SDK-only `joinSession` path. Dropped bare into
   the DOM in Standard mode, the ring renders as a **bottom-left banner** (user report: "call toast
   shows on bottom left") instead of a centered modal → the callee can't find Accept → calls go to
   "Missed". *Skill ask:* the Standard-mode section should ship the overlay wrapper CSS (or the
   components should self-position as a modal). Our fix: `.cc-call-overlay { position:fixed; inset:0;
   z-index:9999; display:flex; center; pointer-events:none }` with `> * { pointer-events:auto }` and
   `:empty { display:none }`. VERIFIED via two-party web↔web voice+video e2e (both ends connect).

5. **F-mobile-creds — placeholder appId fails silently instead of erroring.** With
   `EXPO_PUBLIC_COMETCHAT_APP_ID=your_app_id_here` (the `.env.example` placeholder), the RN SDK dials
   `https://your_app_id_here.apiclient-us.cometchat.io` — a dead host — and the real-time socket
   never connects: chat presence works (REST login) but the conversation list spins forever and
   incoming calls never arrive. Nothing surfaces the misconfig. *Skill/SDK ask:* the SDK should
   **fail loudly on a placeholder/invalid appId** rather than silently dialing a non-existent host,
   and the native integrate recipe should write the real appId into `.env` (not leave the
   placeholder). (The pipeline-side half of this — the harness not injecting creds — is in
   pipeline-notes.)

## SDK packaging (CometChat product, not docs)
- **RN UI Kit ships uncompiled `.tsx` with type errors.** `@cometchat/chat-uikit-react-native`
  (CometChatCallButtons / CallLogs / Incoming / OutgoingCall) has TS2769/TS2322 in its *own* source,
  so a strict `tsc --noEmit` gate fails on the LIBRARY even though the app's integration is clean and
  it bundles/runs. *Ask:* ship compiled `.d.ts`. (Harness now ignores node_modules-only type errors.)


---
_Rollup feeds Consolidate → `rankedFixBacklog` (each fix tied to the blocker that motivated it, §5.5)._
