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

## Harness defects found by driving the real clients (fin, 2026-07-20)

<!-- harness:android-cometchat-creds -->
- **`coverageGap:`** Native-Android codegen reads the CometChat credentials out of `local.properties`
  (`localProps.getProperty("cometchat.appId", "")`), but **nothing in the pipeline ever wrote those
  keys** — and two writers (`lib/providers.py` AndroidNativeProvider.demo, `lib/mobile.py`
  build_android) truncated the file to `sdk.dir=` on every run. Every fin APK therefore shipped with
  `BuildConfig.COMETCHAT_APP_ID == ""`, logged "CometChat credentials not configured — chat disabled",
  skipped init, and then **hard-crashed the process** on the first SDK call: `CometChat.getLoggedInUser()`
  and `CometChatUIKit.logout()` THROW ("Please call the CometChat.init() method ...") instead of
  returning null/erroring via their callback. Opening the Chat tab or tapping Sign Out threw the user
  to the launcher. Android chat had **never once worked** on this use case.
  - _why verify missed it_: verify proves chat on **web** only; the android leg was never driven, so a
    client that could not initialise chat at all still passed every gate.
  - _fix_: `mobile.write_android_local_properties()` — merges instead of clobbering and injects
    `cometchat.appId/region/authKey` from the UC's `.env.cometchat`; warns when appId resolves empty.

<!-- harness:mobile-incall-screencap -->
- **`falseTrigger:`** `adb screencap` captures the Android in-call screen as a **fully black frame** —
  the CometChat ongoing-call surface is a hardware/WebRTC surface that screencap cannot read. The call
  was genuinely connected at the time (web peer showed both participants + audio activity; the android
  view hierarchy showed "Ongoing call", both participant tiles and a running 01:03 timer matching the
  web timer). **Any vision rubric gated on a mobile in-call SCREENSHOT is a guaranteed false negative.**
  Grade mobile call state from the view hierarchy (`uiautomator dump`) or the peer, never the shot.
  Same class as the existing headless-web call carve-out, different platform.

<!-- harness:ios-cometchat-creds -->
- **`coverageGap:`** The iOS twin of the Android credentials gap. Codegen wires `Info.plist` to
  `$(COMETCHAT_APP_ID)` and reads it via `Bundle.main.infoDictionary`, but scaffolds the xcode build
  settings as `COMETCHAT_APP_ID = ""` / `COMETCHAT_AUTH_KEY = ""` and **nothing ever filled them in**.
  The empty setting substitutes into the plist as an empty string → `AppConfig.cometchatAppID` is nil
  → CometChat never initialises → the chat tab renders the kit's generic **"Oops! Looks like
  something went wrong."**, which reads as a broken UI rather than as missing credentials.
  - _fix_: `mobile.write_ios_cometchat_settings()` patches the pbxproj (Debug AND Release) from the
    UC's `.env.cometchat`, so Xcode-driven builds get the same creds as pipeline-driven ones.

<!-- sdk:ios-header-call-buttons -->
- **`SDK-gap:`** On the explicit-pod iOS calls setup (`CometChatCallsSDK` as its own pod, initialised
  by hand), `CometChatMessageHeader` renders **no call buttons** and there is no supported way to add
  them to it: `hideVoiceCallButton/hideVideoCallButton = false` does nothing (the header only
  populates its built-in pair when the kit's calling data-source is registered, which this path never
  does), and `headerView.tailView.addArrangedSubview(CometChatCallButtons(...))` is silently dropped
  when the header re-lays-out its tail content — the view tree showed NO call-button node at all.
  Workaround: mount `CometChatCallButtons().set(user:).set(controller:)` into the app's OWN view,
  constrained against the header. NB `buildButton(forUser:)` is a subclass override hook and does NOT
  configure the buttons — `set(user:)` is the entry point.

<!-- open:ios-outgoing-call-never-joins -->
- **`SDK-gap:` (OPEN — not fixed)** iOS outgoing call rings the peer and shows the kit's
  outgoing-call screen ("Calling…"), but when the callee accepts, the media session never
  establishes and the caller logs **"Missed Call"**. Android→web and web→Android connect fine on the
  same app/session, so this is iOS-side session establishment, not signalling. Suspected cause: this
  app hand-writes `CometChatCalls.init` with its own pod, while the kit-default additive path expects
  the vendored CallsSDK plus `enable(inAppIncomingCall: true)` ONLY — per `cometchat-ios-calls` §5,
  hand-initialising is the standalone/custom-surface path and the caller must then implement
  `CometChatCallDelegate.onOutgoingCallAccepted` → `generateToken` → `startSession` itself, which
  this app does not do. **iOS is send-capable but not connect-capable until that is resolved.**

## iOS incoming calls RESOLVED + gallery per-platform shots (fin, 2026-07-21)

<!-- resolved:ios-incoming-call -->
- **`SDK-gap:` (RESOLVED)** iOS received NO incoming calls (no ring/toast) though chat + outgoing
  worked. TWO stacked causes, both non-obvious:
  1. **Realtime socket never established.** `CometChatUIKit.init`/login authenticates over REST and
     can fetch conversations, but the websocket that delivers incoming calls + presence was not
     brought up — so the device showed OFFLINE ("Last seen …") and the call listener, though
     registered, never fired. Outgoing still worked because `initiateCall` is REST. Fix:
     `UIKitSettings.autoEstablishSocketConnection(bool: true)` AND an explicit `CometChat.connect()`
     after login AND on the restored-session path (relaunch does not re-establish the socket on its
     own; first connect often returns a transient `WSError 1` then succeeds on retry).
  2. **The kit's `CometChatIncomingCall` VC renders EMPTY on iOS 26** — presented modally, embedded,
     via `.fullScreenCover`, or in a dedicated `UIWindow`, it builds (onAppear/completion fire) but
     draws nothing. Replaced with a custom SwiftUI ring. The ring only actually displayed once it was
     embedded with PROPER view-controller containment (`root.addChild(host)` + `host.view` added to
     `root.view` + `didMove`): a `UIHostingController.view` added as a bare subview, or a
     `.fullScreenCover`/ZStack-sibling of a TabView, never runs its SwiftUI render pass on iOS 26.
     Also disable `enable(inAppIncomingCall: true)` so the kit's own (empty) auto-present doesn't
     occupy the presentation slot. Verified end-to-end: Android(Alice)→iOS(Bob) rings, Accept
     connects, both peers live (iOS ongoing surface renders fine — only the INCOMING VC was broken). iOS OUTGOING also verified end-to-end this session (iOS Bob places → Android Alice rings → accept → both live, 00:52 timer, both audio tiles); the earlier 'Missed Call' was accept-tap timing in automation, not an app defect.

<!-- harness:gallery-per-platform-call-shots -->
- **`falseTrigger:` (harness)** demo_gallery.py appended the SAME web-captured call screenshots
  (`callee-ringing-*`, `caller-ongoing-*`) to BOTH the Android and iOS sections — the browser call UI
  shown under an "Android"/"iOS" heading. Now reads the REAL per-platform mobile captures
  (`mobile-incoming-<plat>-*`, `mobile-ongoing-<plat>-*` from twoparty_mobile) and content-hash-dedups
  so a stale/duplicated shot (twoparty_mobile's pull_shot copies a leftover /tmp capture when the
  accept flow finds no widget) can't appear under two platforms.

## Contact directory "messed up" — avatar collisions + junk users (fin, 2026-07-21)

<!-- codegen:pravatar-u-seed-collision -->
- **`coverageGap:`** Seed-data codegen sets user avatars to `https://i.pravatar.cc/150?u=<uid>`.
  pravatar hashes the `?u` seed onto only ~70 images, so different uids COLLIDE onto the SAME face —
  `fin-usr-002` (Bob) and `fin-usr-003` (Carol) resolved to byte-identical images, so two different
  contacts showed the same avatar in chat and the directory looked "messed up". Fix: use EXPLICIT
  distinct `?img=N` numbers (1–70), which also lets you gender-match names. Applied to fin's seeder;
  the codegen prompt/seed guidance should mandate `?img=N` (never `?u=<seed>`) app-wide.

<!-- harness:cometchat-sample-users-pollute-directory -->
- **`coverageGap:`** A freshly-provisioned (trial) CometChat app ships with 5 DEFAULT sample users —
  `cometchat-uid-1..5` (Andrew Joseph, George Alan, Nancy Grace, Susan Marie, John Paul). They appear
  in the app's Contacts directory alongside the real demo users, so a real customer sees five fake
  strangers. provision-app should DEACTIVATE these sample users right after creating/attaching the
  app. (Deactivated by hand for fin: DELETE /v3/users/<uid>.)

<!-- harness:synthetic-probe-users-pollute-directory -->
- **`coverageGap:`** verify's out-of-band chat pair (`fin-cha-001`/`fin-chb-001` = "Chat Alpha/Beta")
  and the moderation probes (`fin-moda-001`/`fin-modb-001` = "Mod ProbeA/B") are created in CometChat
  and never cleaned up, so they also pollute the demo Contacts directory — and a subsequent verify/demo
  run RECREATES them. Probes should deactivate their synthetic users after use (or run against the real
  demo accounts). (Deactivated by hand for fin.)

## Web account-switch showed the previous user's chat (fin, 2026-07-21)

<!-- app:web-logout-doesnt-clear-cometchat -->
- **`coverageGap:`** The web app's `logout()` (Pinia auth store) only cleared its own localStorage
  tokens and NEVER called `CometChatUIKit.logout()`. Combined with the island's `loginOnce`, which
  returned early if ANY user was already logged into the CometChat SDK, switching accounts in the same
  browser left the PREVIOUS user's SDK session live — so the new user's chat rendered the previous
  user's conversations/contacts under scrambled names (reported as "I send to Alice from Bob and it
  goes to Carol"). Fix: pass the current app user's uid into ReactChatApp and have `loginOnce` compare
  it to `getLoggedinUser().getUid()` — if they differ, `CometChatUIKit.logout()` then log the new user
  in. Verified: Alice→(sign out)→Bob in one browser now shows BOB's conversations. Any Vue/React-island
  integration that logs out via app state (not the kit) has this bug — the login path must reconcile
  the SDK session against the intended uid.

<!-- security:ios-authkey-in-tracked-pbxproj -->
- **`coverageGap:`** The iOS build-time creds fix injected COMETCHAT_AUTH_KEY into the TRACKED
  `project.pbxproj`, so the secret-scan gate correctly blocked `push-branch`. The auth key is a
  semi-privileged secret that must never ship in a client app; the iOS client logs in with
  server-minted auth tokens and its init skips `.set(authKey:)` when empty, so the key isn't needed
  on-device. Fix: `write_ios_cometchat_settings` now injects only APP_ID + REGION (public identifiers)
  and actively CLEARS COMETCHAT_AUTH_KEY in the pbxproj. Verified iOS still logs in + chats without it.
