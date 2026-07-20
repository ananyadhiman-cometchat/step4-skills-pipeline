> **UC2 · Community forum (`com`)** — threaded community forum: group discussion with chat + voice/video calls.
> **Stack:** Flutter v6 for web + Android + iOS (**one** codebase spanning all three) · PHP backend — **1 codebase**.
> **CometChat:** Flutter v6 UI Kit + Calls. *Richest ledger — most of the Flutter-calls / go_router cluster lives here.*
> **Gaps recorded: 16.** _Source: `pipeline-state/gaps/com.md` — edit there, not here._

---

## Community forum (com) — backend

- none

## Community forum (com) — app (Flutter v6 · CometChat Calls)

Symptom (observed on android + iOS, 2026-07-11): `CometChatCallButtons(user:, group:)` is placed in the
conversation-thread AppBar and renders normally, but tapping voice/video does NOTHING — no outgoing-call
screen, no error. Verified root causes against `cometchat-flutter-v6-calls` (rules 1.0/1.1/1.7): the
integration was missing `..enableCalls = true` on `UIKitSettingsBuilder`, `CometChatUIKitCalls.init(appId,
region)` in `CometChatUIKit.init`'s `onSuccess`, AND `navigatorKey: CallNavigationContext.navigatorKey`.

Genuine CometChat inconsistencies (skills / docs / product — distinct from the codegen miss):

- **`docsEscape:` `navigatorKey: CallNavigationContext.navigatorKey` is undocumented for the
  `MaterialApp.router` + go_router pattern.** The docs/skill show `MaterialApp(navigatorKey: CallNavigation
  Context.navigatorKey)`, but a modern app uses `MaterialApp.router` (navigation owned by go_router) where
  you CANNOT set `navigatorKey` on `MaterialApp`. The required reconciliation — make go_router's root
  navigator key BE the kit's key (`CallNavigationContext.navigatorKey = _rootGoRouterKey`) — appears nowhere
  in the public Calls-Flutter docs. go_router is the de-facto Flutter routing standard, so this gap hits most
  real apps. Without it `CometChat.initiateCall` succeeds (a real sessionId) but `CallNavigationContext.
  navigatorKey.currentContext` is null → `CometChatOutgoingCall` never mounts → "tap does nothing."

- **`staleness:` the vendor's own v6.0.1 sample app is broken for calls on mobile out-of-the-box.**
  `examples/sample_app/main.dart` sets `navigatorKey: kIsWeb ? CallNavigationContext.navigatorKey : null` —
  i.e. it wires the key ONLY on web and passes `null` on android/iOS, so the outgoing-call screen never mounts
  on a device. A developer who copies the official sample gets non-working calling. (Only the *other* sample,
  `examples/ai_sample_app`, wires it unconditionally — the correct form.)

- **`coverageGap:` `CometChatCallButtons` silently no-ops when its hidden prerequisites are unmet.** The
  documented component renders and looks functional with no `enableCalls`/`UIKitCalls.init`/`navigatorKey` in
  place; there is no assertion, log, or disabled state to signal "calling isn't wired." The component doc does
  not co-locate its three hard prerequisites, so placing the widget as documented yields a dead button.

(The codegen ALSO omitted `enableCalls`/`UIKitCalls.init` — that miss is recorded in pipeline-notes as an
agent gap, not a CometChat gap. Fix path for the app: add `..enableCalls = true`, call `CometChatUIKitCalls.
init(appId, region)` in `onSuccess`, and set `CallNavigationContext.navigatorKey = <go_router rootNavigatorKey>`.)

## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)
<!-- selfheal:compose-env -->
- **`missedTrigger:`** [self-heal:compose-env] The production/deployment skill must document injecting COMETCHAT_* into the RUNTIME deployment env (docker-compose/service), not just .env.example — otherwise the backend mints an EMPTY auth token and the conversation list errors ('Oops') on every client.
  - _auto-repaired by the harness (fix's existence IS the finding)_: injected `${COMETCHAT_*}` refs into the backend compose `environment:` (values in a git-ignored `.env`, so no secrets in the tracked compose).
  - _trigger evidence_: `backend /api/auth/login returned cometchat_auth_token:"" → CometChatConversations rendered "Oops" on web + android + ios`
<!-- selfheal:ios-deploy-target -->
- **`missedTrigger:`** [self-heal:ios-deploy-target] cometchat-flutter-v6-calls / cometchat-ios must document that cometchat_calls_sdk requires an iOS deployment target >= 15.1 (Flutter/RN scaffold 13.0) — `pod install` fails 'requires a higher minimum iOS deployment version' otherwise. Ship the Podfile platform + post_install IPHONEOS_DEPLOYMENT_TARGET.
  - _auto-repaired by the harness (fix's existence IS the finding)_: set `platform :ios, '15.1'` + post_install `IPHONEOS_DEPLOYMENT_TARGET=15.1` + pbxproj; iOS demo build then succeeded.
  - _trigger evidence_: `Error: The plugin "cometchat_calls_sdk" requires a higher minimum iOS deployment version ... increase your application's deployment target to at least 15.1`
<!-- selfheal:cleartext-http -->
- **`missedTrigger:`** [self-heal:cleartext-http] The mobile native-setup skill must document that a RELEASE build talking to a local HTTP backend needs android:usesCleartextTraffic + a network_security_config AND the INTERNET permission in the MAIN manifest (Flutter injects INTERNET only into the DEBUG manifest) + iOS ATS NSAllowsArbitraryLoads.
  - _auto-repaired by the harness (fix's existence IS the finding)_: added INTERNET to the main manifest + usesCleartextTraffic + network_security_config; release apk then reached the backend.
  - _trigger evidence_: `release apk showed "Connection error. Check your network." — aapt: no android.permission.INTERNET in release apk (only in the debug manifest)`


## Skills-critic — app (app)

- staleness: cometchat-flutter-v6-{core,calls,production,troubleshooting} state iOS deployment target 13.0 vs cometchat_calls_sdk 5.0.3 podspec 15.1
    Skills assert iOS **13.0** as the floor in ≥6 places — cometchat-flutter-v6-core/SKILL.md:459 (`platform :ios, '13.0'`), cometchat-flutter-v6-production/SKILL.md:359 + :362 ("CometChat UIKit v6 requires iOS 13.0+. If your Podfile has a lower target, `pod install` will fail" — asserts 13.0 is SUFFICIENT) + :509, cometchat-flutter-v6-calls/SKILL.md:5 ("iOS 13+"), cometchat-flutter-v6-troubleshooting/SKILL.md:702 + :821 + :890. Reality: `~/.pub-cache/.../cometchat_calls_sdk-5.0.3/ios/cometchat_calls_sdk.podspec:20` = `s.platform = :ios, '15.1'`, pulled transitively by the resolved `cometchat_chat_uikit 6.0.5` (calls bundled → the 15.1 floor applies to EVERY v6 app, chat-only included). At 13.0 `pod install` fails ("requires ... at least 15.1"); diff bumped `ios/Podfile` to `platform :ios, '15.1'`. NOTE: same root as the witnessed self-heal:ios-deploy-target above — filed here as the precise doc-side defect (present-but-STALE, not merely "undocumented" as that note framed it): the six 13.0 claims are actively wrong and each is a concrete fix location; production:362's "13.0+ … will fail if lower" is doubly misleading.

### agent (skill was correct; codegen missed it)
- Calls render but are INERT — `CometChatCallButtons(user:, group:)` placed in conversation_thread_screen.dart, but `lib/main.dart:29` `UIKitSettingsBuilder` omits `..enableCalls = true`, there is no `CometChatUIKitCalls.init()` inside `CometChatUIKit.init`'s onSuccess (main.dart:35), and no `navigatorKey: CallNavigationContext.navigatorKey` on the MaterialApp. cometchat-flutter-v6-calls rules 1.0 / 1.1 / 1.7 document ALL THREE explicitly (skill was correct). Matches the runtime log ("call buttons inert (no CometChatUIKitCalls.init, no CallNavigationContext.navigatorKey)"). Already noted as an agent gap in the ChosenPlacement section above.
- `lib/providers/auth_provider.dart` login/register call `CometChatUIKit.loginWithAuthToken(...)` fire-and-forget (not awaited) before `notifyListeners()`, so go_router navigates to /conversations before Chat login resolves. Minor/transient only — `ConversationsBloc._onConnectionStateUpdate` re-issues `LoadConversations(silent:true)` on reconnect (conversations_bloc.dart:1098-1104), so a pre-login mount self-recovers once the socket connects.

### retracted (checked, not a real CometChat gap — why)
- CometChatConversations "Oops" as a UIKit/SDK defect — RETRACTED. Root cause is the already-witnessed self-heal:compose-env (backend minted an empty `cometchat_auth_token`), not a kit bug. Independently verified the kit self-heals a transient pre-login mount: `_onConnectionStateUpdate` re-fetches on `onConnected` (conversations_bloc.dart:1102), so no permanent error state originates in the kit.
- ProGuard `-dontwarn com.cometchat.calls.CometChatRTCView / RTCReceiver / RTCCallback / AnalyticsSettings` as an undocumented R8 requirement — RETRACTED. Documented VERBATIM in cometchat-flutter-v6-production/SKILL.md:257-262 (plus `isMinifyEnabled`/`proguardFiles` at :271-275); the diff's `android/app/proguard-rules.pro` + build.gradle.kts are a faithful copy of that skill, not a gap.
- Missing `..authKey` on UIKitSettingsBuilder (main.dart:29) — RETRACTED. App uses `loginWithAuthToken` (server-token/production path); authKey is not required for init/token-login in that flow (cometchat-flutter-v6-production). Init with appId+region+subscriptionType is valid.
- Possible hallucinated APIs — RETRACTED, all present in the resolved SDK: import `package:cometchat_chat_uikit/cometchat_calls_uikit.dart` (lib/cometchat_calls_uikit.dart exists), `CometChatCallButtons(user:, group:)` (call_buttons constructor), `CometChatConversations.onItemTap` = `Function(Conversation)?` (cometchat_conversations.dart:222), `conversation.conversationWith` User/Group cast (cometchat_helper.dart:33). Also `android.enableJetifier=true` correctly applied per calls rule 1.3.
<!-- selfheal:call-permissions -->
- **`missedTrigger:`** [self-heal:call-permissions] The calls skill should CO-LOCATE the native camera/mic + iOS UIBackgroundModes(audio/voip) requirement with the CometChatCallButtons usage (or ship it via a config plugin that survives regeneration) — without NSCamera/NSMicrophoneUsageDescription, iOS calls silently fail: the call button is inert and an accepted incoming call is immediately 'rejected' (media session can't open).
  - _auto-repaired by the harness (fix's existence IS the finding)_: call perms → ios NSCameraUsageDescription, ios NSMicrophoneUsageDescription, ios UIBackgroundModes, android 8 call perms
  - _trigger evidence_: `iOS Info.plist had no NSCamera/NSMicrophoneUsageDescription; incoming accept → rejected`


## Skills-critic — app (Flutter v6 · calling on virtual devices, 2026-07-14)

- coverageGap: cometchat-flutter-v6-calls testing guide does not warn that WebRTC calls CANNOT connect on emulators/simulators (only signaling works there)
    Confirmed live android-emulator ↔ iOS-simulator: SIGNALING works both ways (caller "Calling…", callee incoming overlay with Accept/Decline), but the MEDIA session (generateToken → joinSession → WebRTC) never establishes — every call ends "Missed"/"rejected" and `CometChatOngoingCall` shows its error state ("Something went wrong", cometchat_ongoing_call.dart:98); server-side call action never reaches `ongoing`. The WebRTC.xcframework DOES ship the ios-arm64_x86_64-simulator slice, and AUDIO-ONLY (voice) fails too, so it is not the arch-exclusion nor the camera — the virtual devices simply can't run the peer WebRTC media pipeline. The skill's checklist says "Runtime (real devices)" but never WARNS that the DEFAULT dev loop (emulator/simulator) will FALSELY show calling as broken. Ask: state explicitly that call verification REQUIRES two physical devices; virtual devices ring-but-never-connect; add that to the testing guide + a troubleshooting entry.

- missedTrigger: iOS CometChatCallButtons initiate is a silent no-op (no outgoing call, no screen) with the same wiring that WORKS on android
    Confirmed live on the iOS simulator: with `..enableCalls=true` + `CometChatUIKitCalls.init` in onSuccess + go-router root key = `CallNavigationContext.navigatorKey` (identical Dart that presents the outgoing "Calling…" screen on android), a PRECISE tap on the iOS voice/video buttons does NOTHING — no `CometChatOutgoingCall`, and Marco's thread logs only Incoming calls, never an Outgoing one (so no call is initiated server-side). iOS RECEIVES fine (incoming overlay shows), so the calls module is up. Ask: cometchat-flutter-v6-calls / cometchat-ios should document the iOS outgoing-call flow requirement that differs from android (or confirm the kit's iOS initiate path), and flag whether this reproduces on a real device vs. is simulator-only. NEEDS a physical iPhone to classify kit-bug vs. simulator-limitation (telehealth confirmed iOS calling connects on real devices).

## Skills-critic — app (Flutter v6 · calling + go_router, resolved via a working reference app 2026-07-14)

- falseTrigger: cometchat-flutter-v6-calls' CometChatCallButtons + CallNavigationContext.navigatorKey are UNUSABLE with go_router / MaterialApp.router (the standard Flutter routing) — the kit's own recipe silently no-ops
    Confirmed against a WORKING production Flutter+CometChat app (Deskline, cometchat-integration branch) that ALSO uses MaterialApp.router + go_router and where calling works on the iOS simulator. Root cause + fix, verified in that app's source:
    (1) The v6 kit presents the outgoing call via `Navigator.push(CallNavigationContext.navigatorKey.currentContext, ...)`. That key is never owned by go_router, so tapping CometChatCallButtons does NOTHING (no outgoing call, no error) — exactly the reported "iOS button does nothing". Neither wiring the go_router root key to CallNavigationContext.navigatorKey NOR a plain-MaterialApp+Router.withConfig conversion fixes it.
    (2) The working app DROPS the kit's calling UI entirely (no `enableCalls`, no CometChatCallButtons, no CallNavigationContext — a code comment there notes "the 5.x SDK does not provide CallNavigationContext — that's a 4.x-kit symbol"). It drives calling on the RAW `cometchat_calls_sdk`: a custom button calls `CometChat.initiateCall` then presents with `Navigator.of(context, rootNavigator: true).push(customCallScreen)` (the button lives INSIDE go_router's tree, so rootNavigator resolves correctly on both platforms), and a custom ongoing-call screen requests mic/cam perms, **explicitly `CometChatCalls.loginWithAuthToken`** (the kit's `enableCalls` was supposed to log the Calls SDK in but did NOT — so `joinSession` failed and incoming ACCEPT was immediately "rejected"), then `CometChatCalls.joinSession`.
    Ask: cometchat-flutter-v6-calls must (a) WARN that CometChatCallButtons + CallNavigationContext.navigatorKey do not work with MaterialApp.router/go_router (the de-facto routing standard) and are silent no-ops there, and (b) SHIP the raw-Calls-SDK + rootNavigator + explicit `CometChatCalls.loginWithAuthToken` recipe as the supported path for go_router apps (init/permissions/joinSession/end + custom incoming listener). Rule 1.0's "enableCalls handles Calls-SDK login internally" is not reliable — document the explicit login.

- SDK-gap: initialising the Calls SDK at STARTUP registers native call handlers that HIJACK incoming calls and background/close the app (android)
    Confirmed vs the working Deskline app: com called the kit's `CometChatUIKitCalls.init` at startup (after chat init). That registers the cometchat_calls_sdk native components (telecom `CometChatCallConnectionService` + `OngoingCallService` seen in the merged manifest / full-screen call notification). On an incoming call these native handlers take over → the Flutter app MINIMIZES then closes on android. Deskline never inits calls at startup — it inits the RAW `CometChatCalls.init` LAZILY (ensureCallsSdkInitialized) only on the call-start path, and handles incoming purely in Dart via the Chat SDK CallListener. Ask: cometchat-flutter-v6-calls / the calls SDK should (a) document that eager Calls-SDK init wires native incoming-call handling that conflicts with a custom Dart incoming UI + backgrounds the app, and (b) recommend lazy init on the call path when the app provides its own incoming UI (or provide a flag to disable the native telecom/notification takeover).

- docsEscape: the Flutter Calls "Join Session" quick-start documents NO login prerequisite, yet joinSession fails with ERROR_AUTH_TOKEN ("User auth token is null") until the Calls SDK is separately logged in
    Confirmed live android + iOS, then fixed and verified end-to-end (android↔iOS calls connect). The genuine gap: the official Join Session page (/calls/flutter/join-session) "Join with Session ID" quick-start says only "Pass a session ID and the SDK automatically generates the token and joins the call" — it never tells you the Calls SDK must be logged in first. But its own error table lists ERROR_AUTH_TOKEN = "User not logged in or auth token invalid", which is exactly what fires. The prerequisite `CometChatCalls.loginWithAuthToken(...)` (before joinSession) is absent from the join recipe. Ask: cometchat-flutter-v6-calls must document the `CometChatCalls.loginWithAuthToken` prerequisite in the join-session flow (init → login → joinSession), for both the outgoing and the accept path.
    NOTE (retraction of an earlier sub-claim): a prior version of this entry also asserted "`CometChat.getUserAuthToken()` returns null after loginWithAuthToken". That is UNVERIFIED and retracted — the live fix logs show the Calls login succeeded via a token captured at app-login time (`source=captured`), so getUserAuthToken() was never exercised. The token API may be fine; do not treat it as a gap without evidence.

- SDK-gap: `CometChatCalls.getLoggedInUser()` is asynchronous (returns `Future<User?>`), so the intuitive `if (getLoggedInUser() != null) …` guard is ALWAYS true and silently skips the required Calls-SDK login
    This was the true root cause of the "User auth token is null" failure (not the token API). `getLoggedInUser()` returns a `Future<User?>`; comparing the Future object to null is always non-null, so an "already logged in?" short-circuit guard returns early WITHOUT ever calling `loginWithAuthToken`, and the subsequent `joinSession` then fails with ERROR_AUTH_TOKEN. The same shape appears in a known-good reference app (Deskline) as a latent bug that only escapes because that app also logs the Calls SDK in during init. Ask: cometchat_calls_sdk / cometchat-flutter-v6-calls should (a) make the async return shape unmistakable in the recipe (always `await getLoggedInUser()`), or (b) provide a synchronous `isLoggedIn`/`getLoggedInUserSync` so the common guard isn't a silent no-op. Verified via analyzer (undefined getter on `Future<User?>`) + live fix (await → calls connect).

- docsEscape: incoming-call caller identity (display name) is not populated on the WebSocket incoming event, so a 1:1 call rings as "Unknown Caller"
    Confirmed live: `onIncomingCallReceived(Call)` fires with the caller present only as a uid — `call.sender?.name` / `call.callInitiator` name are empty on the socket event (the SDK's own Call model comments this: "WebSocket events where sender/receiver may be strings or in data.entities"). Using the SDK field directly shows "Unknown Caller" on the incoming toast. Fix: resolve the name with a separate `CometChat.getUser(uid)` lookup (falling back to callInitiator/sender name) and update the UI. Ask: cometchat-flutter-v6-calls should document that the incoming-call event carries only the caller uid and that the display name must be resolved via getUser (or ship a helper), so integrators don't render "Unknown Caller".

## Skills-critic — web (web)

- none (verified: `cometchat-react-patterns` §2 provider shape matches CometChatProvider.tsx exactly — module-level `initialized`/`loginInFlight` guards, `getLoggedinUser()` casing, `UIKitSettingsBuilder().setAppId().setRegion().setAuthKey().subscribePresenceForAllUsers().build()` → `CometChatUIKit.init(settings)`, `loginWithAuthToken(token)`, `logout()` all confirmed present in resolved `@cometchat/chat-uikit-react@6.5.3` types (dist/index.d.ts:2425/2470/2475/2492); `cometchat-react-calls` §1.4 explicitly sanctions the ZERO-`CometChatCalls.init`/`login` additive path and §1.7 the root-mounted `<CometChatIncomingCall />` — both matched by the diff (calls-sdk pinned `^5.0.1`); chat SDK `^4.1.12` matches patterns §8 `@cometchat/chat-sdk-javascript@^4`.)

### agent (skill was correct; codegen missed it)
- Build error TS2345 at CometChatProvider.tsx:66 — `doLogin(cometchatToken)` passes `string | null` to `(token: string)`.
    The skill's provider (`cometchat-react-patterns` §2) logs in with a literal `ensureLoggedIn("cometchat-uid-1")`, so the skill never hits this. The agent adapted it to a nullable `cometchatToken` from `useAuth()` and relied on the `if (!cometchatToken) return` guard at line 41 — but TS does not narrow a captured variable inside the nested `async setup()` closure, so the type stays `string | null` at line 66. Pure TS-narrowing codegen defect (fix: hoist `const token = cometchatToken` after the guard, or param-type), not a CometChat skill/doc/SDK gap.

### retracted (checked, not a real CometChat gap — why)
- `<CometChatIncomingCall />` rendered without `CometChatCalls.init()`/`login()` — NOT a gap. `cometchat-react-calls` §1.4 states verbatim the common additive/default ringing path needs neither, and both canonical React v6 sample apps mount only `<CometChatIncomingCall />`. Code is correct per skill.
- Chat SDK v4 (`^4.1.12`) paired with UI Kit v6 (`^6.5.3`) — NOT a mismatch. `cometchat-react-patterns` §8 install line prescribes `@cometchat/chat-uikit-react@^6 @cometchat/chat-sdk-javascript@^4`; the pairing is intended.
- `getLoggedinUser` (lowercase 'in') possible typo — NOT a gap. Confirmed the static kit method is `getLoggedinUser()` (dist/index.d.ts:2475); the `getLoggedInUser()` variants at 1945/3328 are instance/SDK-User methods. Code matches skill and SDK.

## Skills-critic — backend/production (server auth-token provisioning · web run 2026-07-14)

- staleness: cometchat-production server recipe detects "user already exists" via `response.status === 409`, but CometChat's create-user returns HTTP **400** with `error.code: ERR_UID_ALREADY_EXISTS`
    Confirmed live against the provisioned app: `POST /v3/users` with an existing uid returns `HTTP 400`, body `{"error":{"code":"ERR_UID_ALREADY_EXISTS","message":"The uid ... already exists ..."}}` — NOT 409. The skill's `createCometChatUser` recipe (cometchat-production/SKILL.md:641-642) branches on `if (response.status === 409) { ...already exists... return; }`, so that branch NEVER fires; on a re-created user the recipe falls through to `throw new Error("Failed to create CometChat user")`. Real impact: any idempotent re-provision (re-seed, retry, signup collision) is treated as a hard failure. Ask: cometchat-production must detect the duplicate via `error.code === 'ERR_UID_ALREADY_EXISTS'` (or status 400 + that code), not HTTP 409. Same 409 assumption appears wherever the "create user then mint token" server recipe is shown.

### agent (skill was correct; codegen missed it)
- Backend `CometChatService::getAuthToken` sent `'avatar' => $user->avatar_url ?? null` — CometChat's create-user REJECTS `avatar: null` (HTTP 400 "The avatar must have a value"), so the create failed, the auth_tokens fallback then failed (user never existed), and avatar-less users (admin/guest/smoke) got an EMPTY auth token → permanently unable to chat / "user not found" when others opened their thread. NOT a skill gap: cometchat-production/SKILL.md:634 shows the correct `...(avatar ? { avatar } : {})` (omit when absent); the PHP codegen deviated. Fix: omit `avatar` from the create payload when empty. (Also surfaced the web hard-gate: an empty/invalid token left the React provider spinning "Connecting to chat…" forever — added a 15s login timeout.)
