# STEP4 · Community Forum (com) — Final Consolidated Report

_Generated 2026-07-14. Use case: com (Community Forum). CometChat app: `step4-com` (`16808422c65e13997`, region us)._

## Scope delivered — web + android + iOS

| Surface | Stack | CometChat | Status |
|---|---|---|---|
| **web** | React + Vite + TS | chat (Conversations, Messages, Users, Calls buttons) | ✅ verified in-browser: login → conversations → **send** → new-chat |
| **android** | Flutter v6 | chat + **voice/video calls** | ✅ calls connect android↔iOS (manually verified) |
| **iOS** | Flutter v6 | chat + **voice/video calls** | ✅ calls connect android↔iOS (manually verified) |
| **backend** | PHP / Laravel | server-minted auth tokens + user provisioning | ✅ healthy; all roles mint valid tokens |

## What works (verified)
- **Mobile calling** android↔iOS both directions — outgoing + incoming (toast UI), accept → connected, caller name resolved.
- **Web chat** — login (backend `cometchat_auth_token`), live conversation list, message thread + history (incl. cross-platform call actions), send, and **"+ New chat"** users list to start a conversation with anyone.
- **Provisioning** — every role (admin/member/moderator/guest) is created in CometChat and gets a valid token.

## Fixes applied (this engagement)
**Mobile (Flutter):**
1. Lazy raw Calls-SDK init (startup init hijacked incoming calls, backgrounding the app).
2. `await CometChatCalls.getLoggedInUser()` — the async guard was always-true and silently skipped the Calls login (the true "User auth token is null" cause).
3. Capture + persist the CometChat auth token at login (getUserAuthToken unreliable after loginWithAuthToken).
4. Resolve incoming caller name via `callInitiator`/`getUser` (no "Unknown Caller").
5. Custom raw-SDK call widgets + rootNavigator (kit's `CometChatCallButtons`/`CallNavigationContext` are no-ops under go_router).

**Web (React):**
6. `+ New chat` users list (`CometChatUsers`) to start new conversations.
7. 15s login timeout so an invalid token shows an error instead of an infinite spinner.
8. TS closure-narrowing fix (`const token` after the null guard).

**Backend (Laravel):**
9. **Omit `avatar` when absent** — CometChat's create-user rejects `avatar: null` (HTTP 400), which left avatar-less users (admin/guest/smoke) with an EMPTY token and unprovisioned. Root cause of "stuck loading" + "user not found".
10. Detect duplicate uid via `ERR_UID_ALREADY_EXISTS` (CometChat returns 400, not 409).

## Genuine CometChat gaps recorded (→ MASTER_GAPS.md, 18 total)
- **docsEscape (3):** Calls Join-Session prerequisite (`CometChatCalls.loginWithAuthToken`) undocumented; incoming-call event carries only the caller uid → "Unknown Caller" without a `getUser` lookup; `navigatorKey` reconciliation for `MaterialApp.router`/go_router.
- **SDK-gap (2):** eager Calls-SDK init wires native incoming handling that backgrounds the app; `CometChatCalls.getLoggedInUser()` is async (`Future<User?>`) so the intuitive `!= null` guard is a silent no-op.
- **staleness (3):** iOS deploy-target 13.0 vs calls-sdk 15.1 podspec; vendor sample wires the call navigator key on web only; **cometchat-production server recipe checks `status === 409` for duplicate uid but CometChat returns 400 `ERR_UID_ALREADY_EXISTS`.**
- **coverageGap (2), missedTrigger (7), falseTrigger (1)** — see MASTER_GAPS.md.
- **cometchat-react skill: NO genuine gaps** (skills-critic verified the provider shape, zero-init calls path, SDK pairing, method casing; retracted 3 would-be gaps). Agent codegen slips (TS narrowing, avatar:null) recorded as agent gaps, not CometChat gaps.

## Pipeline mechanism added
- **`STEP4_ONLY` scoping** — `build`/`integrate` touch only the targeted component; scoped `integrate` skips the destructive `reset --hard main`, so a verified component (com's Flutter app) is never regenerated. Enabled the web-only run without touching mobile.

## Git state
- com repo `feature/cometchat-integration` @ `61bd368` — all fixes committed; Flutter app intact; **zero secret files tracked**.
- automate repo `pipeline/reliability-revamp` @ `bc77593` — pipeline scoping + gaps committed.
- **Push remains human-gated.**
