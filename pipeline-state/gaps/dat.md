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
**Owner: skills/sdk (CometChat React Native UIKit version compatibility)**
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
