> **UC1 · Marketplace (`mkt`)** — buyer/seller marketplace: listings, orders, and in-app chat + calls between buyer and seller.
> **Stack:** Next.js web · React Native (Expo) for Android + iOS (one shared codebase) · Python backend — **2 codebases**.
> **CometChat:** React UI Kit (web) + React Native UI Kit (mobile) + Calls SDK.
> **Gaps recorded: 7.** _Source: `pipeline-state/gaps/mkt.md` — edit there, not here._

---

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

3. **`missedTrigger:`** **Web message-list does not scroll (recurring).** The CometChat UI Kit message list needs a
   bounded-height / `overflow` container; the skill's mount layout doesn't provide one, so the list
   grows unbounded and never scrolls. *Skill ask:* the mount recipe should ship the bounded-height
   wrapper (we used `.cc-msg-list { flex:1 1 0; min-height:0; height:100%; overflow:hidden }` plus a
   child rule for the kit's auto-injected `.cometchat` element).

4. **`SDK-gap:`** **F-web-call — prebuilt call components have no positioning for Standard mode.**
   `cometchat-react-calls` mounts `<CometChatIncomingCall />` / `<CometChatOutgoingCall />` at root
   but gives fixed/inset overlay guidance ONLY for the SDK-only `joinSession` path. Dropped bare into
   the DOM in Standard mode, the ring renders as a **bottom-left banner** (user report: "call toast
   shows on bottom left") instead of a centered modal → the callee can't find Accept → calls go to
   "Missed". *Skill ask:* the Standard-mode section should ship the overlay wrapper CSS (or the
   components should self-position as a modal). Our fix: `.cc-call-overlay { position:fixed; inset:0;
   z-index:9999; display:flex; center; pointer-events:none }` with `> * { pointer-events:auto }` and
   `:empty { display:none }`. VERIFIED via two-party web↔web voice+video e2e (both ends connect).

5. **`missedTrigger:`** **F-mobile-creds — placeholder appId fails silently instead of erroring.** With
   `EXPO_PUBLIC_COMETCHAT_APP_ID=your_app_id_here` (the `.env.example` placeholder), the RN SDK dials
   `https://your_app_id_here.apiclient-us.cometchat.io` — a dead host — and the real-time socket
   never connects: chat presence works (REST login) but the conversation list spins forever and
   incoming calls never arrive. Nothing surfaces the misconfig. *Skill/SDK ask:* the SDK should
   **fail loudly on a placeholder/invalid appId** rather than silently dialing a non-existent host,
   and the native integrate recipe should write the real appId into `.env` (not leave the
   placeholder). (The pipeline-side half of this — the harness not injecting creds — is in
   pipeline-notes.)

6. **`SDK-gap:`** **F-web-ongoing — ongoing-call screen doesn't fill the viewport (Standard mode).** Same family
   as #4 but for the *connected* call: after Accept, `<CometChatOngoingCall>` renders in a bounded
   box (~top ⅔ of the page) instead of full-screen, so the **conversation thread bleeds through
   below the call controls** (Missed Call / Outgoing Call / Call Answered chips visible under the
   hang-up bar) and the remote participant tile/name label duplicates (a "Sara Seller" label appears
   both top-right and bottom-left). *Skill ask:* the Standard-mode prebuilt call components need a
   documented full-viewport container (`position:fixed; inset:0` / `100vw×100vh`) — the skill only
   spells this out for the SDK-only `joinSession` path, so the ongoing screen inherits whatever
   height its parent gives it. Ties into the same overlay fix as #4 but the ongoing surface needs
   its own full-bleed sizing. Observed in the web↔web/mobile↔web call e2e. **WEB-ONLY** — mobile
   already renders the ongoing call in `absoluteFill` (full-screen via CallSurfaces).
   **PARTIAL FIX (verified 2026-07-09):** `.cometchat-ongoing-call { position:fixed; inset:0;
   100vw×100vh; z-index:10000 }` (web/app/globals.css) makes the RECEIVER's ongoing screen
   full-bleed — verified full-screen on the callee, no header/chat bleed. The CALLER's connected
   view is a *different, in-flow* container the kit renders below the app header, so the header
   still shows on the caller side; the complete fix needs the skill to ship a full-viewport wrapper
   for BOTH call surfaces. (An `.cc-call-overlay:not(:empty)` opaque backdrop is NOT viable — the
   idle overlay isn't reliably `:empty`, so it covers the app and blocks clicks.)

## SDK packaging (CometChat product, not docs)
- **`SDK-gap:`** **RN UI Kit ships uncompiled `.tsx` with type errors.** `@cometchat/chat-uikit-react-native`
  (CometChatCallButtons / CallLogs / Incoming / OutgoingCall) has TS2769/TS2322 in its *own* source,
  so a strict `tsc --noEmit` gate fails on the LIBRARY even though the app's integration is clean and
  it bundles/runs. *Ask:* ship compiled `.d.ts`. (Harness now ignores node_modules-only type errors.)
