# dat — CometChat skills/SDK/docs inconsistencies (self-heal witnessed)

## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)
<!-- selfheal:cleartext-http -->
- **`missedTrigger:`** [self-heal:cleartext-http] The mobile native-setup skill must document that a RELEASE build talking to a local HTTP backend needs android:usesCleartextTraffic + a network_security_config AND the INTERNET permission in the MAIN manifest (Flutter injects INTERNET only into the DEBUG manifest) + iOS ATS NSAllowsArbitraryLoads.
  - _auto-repaired by the harness (fix's existence IS the finding)_: rn: usesCleartextTraffic + iOS ATS
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`
<!-- selfheal:web-call-css-vars -->
- **`SDK-gap:`** [self-heal:web-call-css-vars] The CometChat web calls SDK (@cometchat/calls-sdk-javascript) sizes its tile-grid <div> with an INLINE height: calc(100% - var(--cometchat-calls-call-footer-height) - var(--cometchat-calls-call-header-height)) but references those two custom properties WITHOUT ever defining them (each appears exactly once — this calc — in the SDK bundle; the UI Kit doesn't define them either). An undefined var() in calc() is invalid at computed-value time → height computes to 0px → the ongoing-call grid collapses → the SDK's ResizeObserver throws "Container dimensions and number of tiles must be positive" and the call renders collapsed (proven: undefined-var calc → 0px, defined → 674px). The SDK must define these variables itself, or use fallbacks in the calc (var(--x, 0px)). Workaround (auto-applied by the web build gate): define both in the app's global stylesheet :root.
  - _auto-repaired by the harness (fix's existence IS the finding)_: defined call-height CSS vars in src/index.css
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`
<!-- selfheal:compose-env -->
- **`missedTrigger:`** [self-heal:compose-env] The production/deployment skill must document injecting COMETCHAT_* into the RUNTIME deployment env (docker-compose/service), not just .env.example — otherwise the backend mints an EMPTY auth token and the conversation list errors ('Oops') on every client.
  - _auto-repaired by the harness (fix's existence IS the finding)_: backend env → ${COMETCHAT_*} refs (values in git-ignored .env; no secrets in tracked compose)
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`


### CometChat RN UIKit requires RN >= 0.76, incompatible with Expo SDK 51 (RN 0.74.5)
**`SDK-gap:`** **Owner: skills/sdk (CometChat React Native UIKit version compatibility)**
Integrate installed `@cometchat/chat-uikit-react-native@5.3.10`, which pulls `@cometchat/cards-react-native@1.0.0`
with a hard `peer react-native@">=0.76.0"`. dat is scaffolded on **Expo SDK 51 → React Native 0.74.5**, so:
- `npm install` ERESOLVEs (cards-react-native RN>=0.76 vs installed 0.74.5; also datetimepicker@9.1.0 vs expo@51).
- The iOS native build fails to compile `react-native-gesture-handler` (`RCTTurboModuleWithJSIBindings.h` not
  found — a RN 0.76+/new-arch header), because the drifted dep tree also forces RNGH 3.x (needs RN 0.78+).
Result: dat's **mobile** CometChat integration cannot build on iOS at all — yet verify still passed GREEN
because the verify chat proof is WEB-only and mobile is "deferred to the demo boot-2 matrix" (coverage gap:
a mobile-primary app can ship a fully-broken mobile CometChat build while verify reports chat works).
**What CometChat should provide:** the RN UIKit docs/skill must state the React-Native FLOOR per UIKit
version, and codegen must pin a `@cometchat/chat-uikit-react-native` version whose RN peer range includes the
app's RN (Expo SDK 51 → RN 0.74.5 needs a UIKit line that supports RN 0.74, OR the app must be scaffolded on
Expo SDK 52+/RN 0.76+). Same class as the earlier Android v6 "needs calls-sdk peer" surprises.

### iOS "chat doesn't load" — RESOLVED, NOT a CometChat gap (was an app API-URL config bug) [corrected]
**Owner: harness/app-config (NOT skills/sdk) — kept as an audit trail of a misdiagnosis**
Initially logged here as "CometChat chat SDK never reaches ready on iOS". That was WRONG. Root cause, found by
surfacing the provider phase in the UI: the Chat screen sat at phase **`idle`** — i.e. `cometchatAuthToken` was
empty, so CometChat init/login never even started. Why the token was empty: the RN app reads a SINGLE
`EXPO_PUBLIC_API_URL` for both platforms, and `.env` pins it to `http://10.0.2.2:8080` (the ANDROID-emulator host
alias). iOS can't reach `10.0.2.2` → login silently failed → no backend token → no CometChat token → spinner.
Compounded by the iOS sim running a STALE baked `main.jsbundle` (standalone build, ignores Metro), so no JS fix
reached it until a rebundle. **Fix (committed a7e8a0b1):** `client.ts` rewrites `10.0.2.2→localhost` on non-Android;
provider surfaces phase/error + a 20s watchdog instead of an infinite spinner. Verified: fresh member1 login on the
iOS sim → CometChat conversation list + thread render. CometChat itself was never the problem. The `RCTVideoManager`
vs `CometChatVideoManager` bridge-name collision is a benign warning (last-registered wins), unrelated to this.
**iOS native follow-up (real, remaining):** the running sim app is a stale standalone build; rebuild it properly
(`expo run:ios` / xcodebuild) so the client.ts fix is baked in durably rather than bundle-swapped.

### CometChat web call surfaces (incoming ring + ongoing call) need an app-provided full-viewport overlay
**`SDK-gap:`** **Owner: skills/sdk (CometChat React UIKit calling — placement)** — RECURS: mkt #4/#6 (React Standard-mode ring/ongoing positioning), del (Angular ongoing-call zero-dimension). Same cross-family placement gap in ≥3 UCs.
The React kit's `<CometChatIncomingCall/>` and the ongoing-call surface render INLINE wherever they're mounted:
the incoming ring rendered off-flow (invisible to the callee) and the caller's ongoing call collapsed inside the
match-page chat card. The kit does not self-promote to an overlay. Fix (dat, commit d90121d8): wrap
`<CometChatIncomingCall/>` in a fixed, centered `.cc-call-overlay` (`:has()`-gated so it never blocks clicks when
idle) and force `.cometchat-ongoing-call` to `position:fixed; inset:0`. The outgoing modal ships its own
`__backdrop` and is fine. Same family as the Angular ongoing-call zero-dimension gap — the kit should document a
required full-viewport wrapper for the incoming/ongoing call components (React + Angular both).

## Recurring gaps also hit on dat (recorded per-UC by design — recurrence is the signal)

> These CometChat gaps first surfaced on earlier UCs and RE-OCCURRED on dat. Recorded here (not just
> de-duplicated) so the per-UC recurrence count reflects that they keep hitting the catalog.

- **`coverageGap:`** RN **additive calling is a silent no-op until `CometChatCalls.init` is called** — the
  header voice/video buttons (`CometChatCallButtons` in `CometChatMessageHeader`) render and look functional,
  but tapping them does NOTHING (no outgoing screen, no error, no disabled state) until an explicit
  `CometChatCalls.init({appId,region,authKey})` runs after `CometChatUIKit.init` (skill: cometchat-native-calls
  §5). dat's generated provider omitted it → inert buttons. RECURS: **com** ("`CometChatCallButtons` silently
  no-ops when its hidden prerequisites — enableCalls / UIKitCalls.init / navigatorKey — are unmet"). Ask: the
  call-button component should co-locate its init prerequisite and surface a disabled/error state when calling
  isn't wired, rather than rendering a dead button.

- **`missedTrigger:`** a **placeholder / empty CometChat appId fails silently** instead of erroring — with an
  empty `VITE_COMETCHAT_APP_ID` (web) / placeholder `EXPO_PUBLIC_COMETCHAT_APP_ID` (mobile) the SDK dials a
  dead host and the socket never connects (chat spins, calls never arrive) with nothing surfaced. dat needed a
  build-gate self-heal (web-cometchat-creds) to inject the real appId. RECURS: **mkt #5** (F-mobile-creds —
  `your_app_id_here` silently dials `https://your_app_id_here.apiclient-us.cometchat.io`). Ask: the SDK should
  fail loudly on a placeholder/invalid appId, and the integrate recipe must write the real appId into `.env`.

- **`missedTrigger:`** the **web message list needs an explicit bounded-height wrapper to scroll** — the kit
  injects a `.cometchat` element that grows unbounded unless the host gives it `height:100%; min-height:0;
  overflow:hidden`; without it the list never scrolls. dat carries the fix in `src/index.css`
  (`.cc-msg-list > .cometchat { height:100%; overflow:hidden }`). RECURS: **mkt #3** (same bounded-height
  requirement). Ask: the React mount recipe should ship the bounded-height wrapper as part of the placement.
