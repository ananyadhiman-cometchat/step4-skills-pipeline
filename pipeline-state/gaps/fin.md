# fin — CometChat skills/SDK/docs inconsistencies (self-heal witnessed)

## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)
<!-- selfheal:web-call-css-vars -->
- **`SDK-gap:`** [self-heal:web-call-css-vars] The CometChat web calls SDK (@cometchat/calls-sdk-javascript) sizes its tile-grid <div> with an INLINE height: calc(100% - var(--cometchat-calls-call-footer-height) - var(--cometchat-calls-call-header-height)) but references those two custom properties WITHOUT ever defining them (each appears exactly once — this calc — in the SDK bundle; the UI Kit doesn't define them either). An undefined var() in calc() is invalid at computed-value time → height computes to 0px → the ongoing-call grid collapses → the SDK's ResizeObserver throws "Container dimensions and number of tiles must be positive" and the call renders collapsed (proven: undefined-var calc → 0px, defined → 674px). The SDK must define these variables itself, or use fallbacks in the calc (var(--x, 0px)). Workaround (auto-applied by the web build gate): define both in the app's global stylesheet :root.
  - _auto-repaired by the harness (fix's existence IS the finding)_: defined call-height CSS vars in src/assets/main.css
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`
<!-- selfheal:ios-companion-pods -->
- **`SDK-gap:`** [self-heal:ios-companion-pods] CometChat's iOS pods are shipped-incomplete: CometChatSDK 4.1.x imports CometChatStarscream (its WebSocket lib) and CometChatUIKitSwift 5.1.x imports CometChatCardsSwift, but a by-the-book `pod install` neither vends nor declares either — so the target fails to compile with "no such module 'CometChatStarscream' / 'CometChatCardsSwift'". The published UIKit/SDK podspecs must declare these as dependencies (or vend the sub-frameworks). Workaround (auto-applied by the build gate): add CometChatStarscream 1.0.2 via a local podspec pointing at the CDN xcframework (library.cometchat.io/ios/v4.0/xcode15/CometChatStarscream_1_0_2.xcframework.zip) + CometChatCardsSwift '~> 1.1'. This is NOT an Xcode/Swift-version issue and NOT fixable by switching to SPM (empty stubs link but crash at launch: Symbol not found WebSocketEvent).
  - _auto-repaired by the harness (fix's existence IS the finding)_: added CometChatStarscream(podspec)+CometChatCardsSwift to 1 Podfile(s)
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`


<!-- skills:android-v6-incoming-call-signature -->
- **`hallucination:`** [cometchat-android-v6-calls] The skill documents `CometChatIncomingCall` as taking
  no required arguments — `CometChatIncomingCall(modifier = Modifier.fillMaxSize())` (SKILL.md:302),
  the component table `CometChatIncomingCall(modifier)` (SKILL.md:346), and
  `CometChatIncomingCall()` (references/add-calls-to-existing-chat.md:57), described as "renders
  nothing when no call active". **That does not compile.** The real composable in
  `chatuikit-compose-android:6.0.3` takes the Call as its FIRST, non-defaulted parameter:
  `CometChatIncomingCall(call: com.cometchat.chat.core.Call, modifier: Modifier, viewModel:
  CometChatIncomingCallViewModel, style: ..., ...)` (verified via javap on the shipped AAR).
  Following the skill verbatim fails the Kotlin build with
  `MainActivity.kt: No value passed for parameter 'call'`.
  - _impact_: every Android v6 Compose use case that mounts the incoming-call overlay per the skill's
    root-mount rule (1.7) fails to compile. The skill's own "canonical wiring" snippet is the failing
    line, so this is not an edge case — it is the documented happy path.
  - _fix the docs need_: show the app owning the incoming-call state and mounting the overlay only
    while ringing, e.g. add a `CometChat.CallListener` (onIncomingCallReceived / onIncomingCallCancelled)
    into a `mutableStateOf<Call?>` and render `incomingCall?.let { CometChatIncomingCall(call = it, ...) }`.
    If the kit is instead meant to source the call from its own view-model, then `call` needs a default —
    the docs and the API currently disagree.
  - _marker note_: labelled `hallucination:` because the documented signature does not exist in the
    SHIPPED artifact I verified (chatuikit-compose-android 6.0.3, the version `6.0.+` resolves to).
    If an earlier 6.0.x genuinely exposed a no-arg overlay, re-file this as `staleness:` — only
    6.0.3 was available locally to check.
  - _workaround applied_: MainActivity.kt wires the listener and passes `call =` explicitly.

<!-- sdk:ios-calls-sdk-absent -->
- **`SDK-gap:`** [cometchat-ios / iOS Podfile] Integrate codegen produced an iOS Podfile containing ONLY
  `pod 'CometChatUIKitSwift', '~> 5.1'` — no `CometChatCallsSDK` at all. The UIKit does NOT pull the
  calls engine transitively, so the app links the calling **UI** (the `CometChatIncomingCall` banner
  renders, which reads as "calling works") while `CometChat.initiateCall` fails at runtime with
  **"Framework not installed please install"** and no call is ever placed. Silent at compile time.
  - _impact_: every native-iOS use case that wires calling per the UIKit docs alone ships with calls
    dead-on-arrival, and nothing in the build catches it.
  - _fix the docs/kit need_: state that `CometChatCallsSDK` is a REQUIRED separate pod for calling
    (alongside the I7 companions), or have the UIKit declare it as a dependency when calling is used.
  - _harness fix applied_: `selfheal._fix_ios_calls_sdk_version` now ADDS `pod 'CometChatCallsSDK',
    '~> 5.0'` when absent — it previously only bumped an existing 4.x pin, so on a Podfile with no pin
    it silently no-op'd ("nothing to bump") and the intended 5.0 pin never applied.

<!-- sdk:ios-i7-x86_64-and-empty-starscream -->
- **`SDK-gap:`** [CometChatUIKitSwift / CometChatSDK packaging] Two further I7 failure modes, beyond the
  known "companion modules aren't bundled":
  (a) **x86_64 cannot resolve the companion module.** With the companion pods correctly installed, the
  arm64 slice compiles but the x86_64 simulator slice still fails
  `cannot find type 'CometChatCardsSwift' in scope` while type-checking
  `CometChatUIKitSwift.swiftmodule/x86_64-apple-ios-simulator.private.swiftinterface` — that interface
  imports `CometChatSDK` but never imports `CometChatCardsSwift`, whose types it references. Both archs
  ship complete slices, so this is an interface-generation defect, not a packaging omission.
  (b) **CometChatSDK materialises an EMPTY CometChatStarscream.framework.** Xcode extracts
  `XCFrameworkIntermediates/CometChatSDK/CometChatStarscream.framework/CometChatStarscream` at 0 bytes
  (apparently off the `CometChatStarscream.swiftinterface` files shipped inside the SDK's dSYMs), and
  the linker then picks that over the real 634KB binary from the CometChatStarscream pod:
  `ld: file is empty`. It persists in shared DerivedData, so retries keep failing after the real
  problem is fixed.
  - _workarounds applied (harness)_: build the simulator arm64-only (`EXCLUDED_ARCHS=x86_64`) and give
    the iOS gate a FRESH per-run `-derivedDataPath`. NB adding `import CometChatCardsSwift` to the
    consuming Swift files does NOT help — verified by building with and without it.
<!-- selfheal:compose-env -->
- **`missedTrigger:`** [self-heal:compose-env] The production/deployment skill must document injecting COMETCHAT_* into the RUNTIME deployment env (docker-compose/service), not just .env.example — otherwise the backend mints an EMPTY auth token and the conversation list errors ('Oops') on every client.
  - _auto-repaired by the harness (fix's existence IS the finding)_: backend env → ${COMETCHAT_*} refs (values in git-ignored .env; no secrets in tracked compose)
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`


<!-- sdk:cometchat-createuser-400-not-409 -->
- **`SDK-gap:`** [CometChat REST /v3/users] Creating a user whose uid already exists returns
  **HTTP 400 with `error.code = ERR_UID_ALREADY_EXISTS`**, NOT the conventional **409 Conflict**:
  `{"error":{"message":"The uid <x> already exists...","code":"ERR_UID_ALREADY_EXISTS"}}`.
  Any idempotent-provisioning routine written the standard way — "201 created, 409 already exists,
  anything else is an error" — therefore throws on every call after the first.
  - _impact_: server-side auth-token minting silently breaks for EVERY returning user. The FIRST login
    for a new uid succeeds (201) and every subsequent login throws, so `cometchat_auth_token` comes back
    empty and that user's chat stops working — while the app's own login still returns 200, so nothing
    upstream notices. On fin this hit immediately, because verify's out-of-band pair seeding had already
    created the very uids the app then tried to provision.
  - _the harness taught this too_: `pipeline/prompts/integrate.md.tmpl` literally instructs
    "call an idempotent CometChat `createUser` (409 = already-exists = ok)", so codegen implements the
    409-only check and inherits the bug. Prompt corrected alongside this entry.
  - _fix the API/docs need_: return 409 for a duplicate uid, or document prominently that
    already-exists is 400 + ERR_UID_ALREADY_EXISTS so integrators branch on error.code, not status.
  - _workaround applied_: CometChatService.isAlreadyExists() accepts 409 OR (400 AND body contains
    ERR_UID_ALREADY_EXISTS); the failure path now includes the response body, since a bare status code
    made this indistinguishable from a credentials or payload error.
