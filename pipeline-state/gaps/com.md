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
