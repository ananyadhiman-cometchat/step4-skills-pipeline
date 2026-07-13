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

