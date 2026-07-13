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

