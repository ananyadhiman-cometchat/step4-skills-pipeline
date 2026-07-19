## Delivery (del) — backend

- coverageGap: "CometChat REST API error code for duplicate user creation (POST /users with existing UID)" — `ERR_BAD_REQUEST` is confirmed from the error-guide, but was not listed under User Errors section specifically; inferred from the general errors table.
- docsEscape: REST API returns 400 `ERR_BAD_REQUEST` for duplicate UID on user create (not 409); had to cross-reference the error-guide page to confirm and cannot find explicit documentation of this specific case in the users/create page.

## Delivery (del) — ios (CometChat UIKit Swift)

> ✅ **RESOLVED — the "un-compilable" conclusion below was WRONG (corrected 2026-07-16). iOS now BUILD
> SUCCEEDED.** This is the recurring **I7** gap (also hit on telehealth/marketplace/edtech). The REAL,
> narrow gap: `CometChatSDK 4.1.6` imports `CometChatStarscream` and `CometChatUIKitSwift 5.1.16` imports
> `CometChatCardsSwift`, but the default pods **reference these companion modules without bundling or
> declaring them** → `no such module` (the textual `.swiftinterface`'s dangling imports). They are NOT
> "statically merged / never shipped" and it is NOT an Xcode/Swift-version problem (installing the exact
> Xcode 26.2 was a red herring). Both modules are obtainable — add them explicitly (CocoaPods, not SPM):
> - `CometChatStarscream` 1.0.2 — a real xcframework on CometChat's CDN
>   (`library.cometchat.io/ios/v4.0/xcode15/CometChatStarscream_1_0_2.xcframework.zip`); vend via a local
>   `CometChatStarscream.podspec`.
> - `CometChatCardsSwift` `~> 1.1` — a normally-published pod, just not pulled transitively.
> Then `pod install` (UTF-8 locale) + build to a CONCRETE simulator. Once the imports resolve, the interface
> compiles regardless of the exact compiler build. Verified: BUILD SUCCEEDED, frameworks embedded
> (CometChatStarscream/SDK/UIKitSwift.framework). Do NOT reconstruct empty stubs (link OK but crash at
> launch: `Symbol not found: WebSocketEvent`). Fix landed in runs/del/ios (Podfile + podspec, commit 7e67fcd);
> harness follow-up: the iOS build_gate / codegen should add these two companion pods for every iOS use case.
> The **staleness** finding below (docs claim "Xcode 16+, Swift 5.0+"; version-pin drift) is still valid.
> The "SDK-gap" bullets below are the ORIGINAL (wrong-conclusion) investigation — kept for the audit trail.

- SDK-gap: CometChat's iOS **binary xcframeworks cannot be compiled on Xcode 16.4 (Swift 6.1.2)**, though
  16.4 is a current release. `CometChatSDK 4.1.6` and `CometChatUIKitSwift 5.1.16` are shipped as binary
  frameworks built with **Swift 6.2.3**; a 6.1.2 compiler rejects them with
  `failed to build module 'CometChatSDK/CometChatUIKitSwift'; this SDK is not supported by the compiler
  (built with Apple Swift 6.2.3 … while this compiler is 6.1.2). Please select a toolchain which matches
  the SDK.` The textual `.private.swiftinterface` fallback ALSO fails because it references transitive
  modules that are not exposed to the app target: `no such module 'CometChatStarscream'` (SDK's WebSocket
  lib) and `no such module 'CometChatCardsSwift'` (UIKit's cards module). Net: the iOS SDK is
  **un-compilable on this machine** regardless of app code — a hard packaging/toolchain-pinning gap that
  blocks every iOS use case here until Xcode is updated to a Swift-6.2.3 toolchain (Xcode 16.5+/26).
- SDK-gap: (packaging, SHARPER — confirmed on Xcode 26.3): the binaries are pinned to the EXACT Swift build
  that compiled them, not "any Swift ≥ 6.2.3". `CometChatSDK`/`CometChatUIKitSwift` xcframeworks ship ONLY
  `CometChat{SDK,UIKitSwift}.swiftmodule` in their `Modules/` dir — the sub-modules their `.private.swiftinterface`
  imports (`CometChatStarscream` in SDK, `CometChatCardsSwift` in UIKit) are statically MERGED in and NOT
  shipped as consumable modules (they appear only inside the dSYMs). Consequence: the textual-interface
  (library-evolution) consumption path is BROKEN on every compiler — `error: Unable to find module
  dependency: 'CometChatCardsSwift'/'CometChatStarscream'` — so the ONLY working path is loading the binary
  `.swiftmodule`, which requires the EXACT compiler build (swiftlang 6.2.3.3.21 = Xcode 26.2). Xcode 26.3
  (Swift 6.2.4) is one patch newer → forces the interface fallback → hard fail. So the real requirement is
  "Xcode 26.2, exactly", which is neither documented nor discoverable, and any future Xcode point release
  silently breaks the SDK until CometChat reships. A binary SDK should ship consumable sub-module interfaces
  (or vend the sub-frameworks) so the library-evolution path works across compiler patches.
- SDK-gap: (CONCLUSIVE — the frameworks are un-consumable as distributed, proven by exhaustive elimination):
  On the EXACT compiler Xcode 26.2 / Swift 6.2.3 (swiftlang-6.2.3.3.21, matching the framework build), del's
  iOS STILL fails. The UIKit/SDK xcframework simulator slice ships ONLY `.swiftinterface` +
  `.private.swiftinterface` (+ .swiftdoc/.abi.json) in its `Modules/CometChat*.swiftmodule/` dir — there is
  **NO binary `.swiftmodule`** — so Xcode is forced to compile the textual interface. That interface
  `import`s `CometChatCardsSwift` (UIKit) and `CometChatStarscream` (SDK), which are NOT installed:
  `CometChatCardsSwift.xcframework` is vended by NO published UIKit version (5.1.11–5.1.16 checked), and
  although `CometChatSDK` 4.1.6's podspec lists `Vendors/CometChatStarscream.xcframework`, a clean
  `pod install --repo-update` does NOT produce it (declared-but-absent from the distribution). Ruled out:
  (1) newer compiler (26.3/6.2.4 → interface fallback), (2) EXACT compiler (26.2/6.2.3 → still builds the
  interface, no binary module to load), (3) `SWIFT_ENABLE_EXPLICIT_MODULES=NO`, (4) clean pod repo-update
  reinstall. Net: **CometChatUIKitSwift 5.1.16 / CometChatSDK 4.1.6 cannot be built for the iOS simulator by
  anyone** — a shipped-broken binary (dangling interface imports to merged-but-unvended sub-modules, no
  binary swiftmodule). This blocks every iOS use case on any machine, not just this one. The Xcode-26.2
  exercise, though it didn't unblock iOS, PROVED it is a CometChat packaging bug, not a local toolchain gap.
  CAVEAT / open question: CometChat iOS apps DO ship in production, so a WORKAROUND exists that this
  investigation did not find — the broken path here is specifically **CocoaPods (`use_frameworks!`) +
  simulator build via `xcodebuild -workspace`**. Untested candidates the pipeline should try before
  declaring iOS dead: (a) **Swift Package Manager** instead of CocoaPods (the SPM distribution may package
  the sub-modules/binary swiftmodules differently), (b) building for a **real device** (`-sdk iphoneos`)
  rather than the simulator slice, (c) a CometChat-support-provided build flag / `module.modulemap` shim, or
  (d) an older SDK/UIKit combo that shipped complete frameworks. The generated integration used the docs'
  default (CocoaPods) — the codegen should be updated to prefer SPM for iOS once a working recipe is
  confirmed. So: "the CocoaPods simulator path is shipped-broken", not "CometChat iOS is impossible".
- staleness: the iOS UI Kit getting-started page states **Requirements: "Xcode 16+, iOS 13.0+, Swift 5.0+"**
  and pins **`pod 'CometChatUIKitSwift', '5.1.9'`** — both inaccurate for the shipped binaries. Xcode 16.4
  (Swift 6.1.2) satisfies "Xcode 16+, Swift 5.0+" yet cannot build the SDK (needs Swift 6.2.3). And the
  version story is inconsistent across THREE numbers: docs pin `5.1.9`, but `~> 5.1` resolves to `5.1.16`;
  worse, `5.1.9`'s own binary is built with **Swift 6.0.2** while its forced dependency `CometChatSDK 4.1.6`
  is built with **6.2.3** — so the documented pin is not even internally consistent. The doc should state
  the true minimum Xcode/Swift for each SDK patch (and ideally ship swiftmodules for the current stable
  Xcode, or a working swiftinterface).

## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)
<!-- selfheal:compose-env -->
- **`missedTrigger:`** [self-heal:compose-env] The production/deployment skill must document injecting COMETCHAT_* into the RUNTIME deployment env (docker-compose/service), not just .env.example — otherwise the backend mints an EMPTY auth token and the conversation list errors ('Oops') on every client.
  - _auto-repaired by the harness (fix's existence IS the finding)_: backend env → ${COMETCHAT_*} refs (values in git-ignored .env; no secrets in tracked compose)
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`


## Delivery (del) — web (CometChat Angular calls)

- SDK-gap: the CometChat **calls SDK** (`@cometchat/calls-sdk-javascript`) sizes its video-tile grid
  `<div class="cometchat-calls-tile-grid-container">` with an INLINE `height: calc(100% -
  var(--cometchat-calls-call-footer-height) - var(--cometchat-calls-call-header-height))`, but it
  **references those two custom properties and never defines them** (each appears exactly once in the SDK
  bundle — this calc — and is set nowhere; the Angular UI Kit doesn't define them either). An undefined
  `var()` in `calc()` (no fallback) is invalid at computed-value time → `height` computes to **`0px`** → the
  grid collapses → the SDK's ResizeObserver throws `Container dimensions and number of tiles must be positive`
  and the call renders collapsed. Proven in-page: undefined-var calc → `0px`; with the vars defined → `674px`.
  The SDK must define these variables itself (or provide fallbacks in the calc, e.g. `var(--x, 0px)`).
  Workaround applied in del/web `styles.scss`: `:root { --cometchat-calls-call-header-height: 60px;
  --cometchat-calls-call-footer-height: 80px; }`.

## Delivery (del) — ios (CometChat calls runtime)

- SDK-gap: (CRASH): after adding `CometChatCallsSDK` (4.2.3, the latest compatible with CometChatSDK 4.1.6 /
  CometChatUIKitSwift 5.1.16), placing/ringing a call WORKS, but **accepting a call CRASHES the app** — white
  screen then `EXC_BAD_ACCESS` (SIGSEGV, "possible pointer authentication failure"). The crashing stack is
  inside **CometChatCallsSDK → facebook::react::invokeInner / RCTNativeModule::invoke** — i.e. the calls SDK
  embeds a **React Native runtime** for its call-session UI, and that RN runtime segfaults on the **arm64 iOS
  26.3 simulator (Xcode 26.2 / Swift 6.2.3)**. CometChatCallsSDK 4.2.3 predates iOS 26. Net: the CometChat
  calls stack that pins to CometChatSDK 4.1.x cannot render an in-call screen on the arm64 iOS-26 simulator —
  iOS voice/video calls are non-functional there regardless of app code (the crash is in the kit's own
  accept→ongoing flow, not app code). Candidate resolutions the pipeline should try: (a) run on a REAL device
  (RN-based SDKs commonly crash on the arm64 sim but work on device), (b) build the sim slice for x86_64 under
  Rosetta (EXCLUDED_ARCHS=arm64 for the simulator), (c) a CometChatCallsSDK build compiled for iOS 26 / the RN
  new architecture. The "Framework not installed" error (fixed by adding the pod) was a SEPARATE, earlier gap.
- SDK-gap: the `CometChatIncomingCall` overlay (mounted full-screen at the tab-bar root) shows an incoming-call
  toast that **intercepts touches across the whole screen**, so a lingering/stuck call makes the entire app
  inaccessible. Compounded by dozens of stuck server-side call sessions (from automated call testing) that
  re-deliver on every login. The overlay should be a hit-test passthrough (only the toast intercepts) and/or
  the app should auto-reject stale incoming calls; there is no clean REST endpoint to end stuck sessions.
- SDK-gap: (CLARIFIED): the call CONNECTS fully — signaling + WebRTC media work end-to-end (verified: the
  Android peer showed a live connected call at 00:47 with working controls after iOS auto-accepted). The ONLY
  failure is the **iOS in-call SCREEN crashing on render** (CometChatCallsSDK 4.2.3 React-Native UI). It
  crashes on BOTH the arm64 iOS-26 simulator AND the x86_64/Rosetta simulator — so it is a hard
  CometChatCallsSDK-RN ⇄ iOS-26-simulator incompatibility, independent of arch. iOS calling is otherwise
  functional (place/ring/connect/media). Fix path: a real iOS device (RN commonly renders on device where the
  sim fails) OR a CometChatCallsSDK build compiled for iOS 26. Rosetta (EXCLUDED_ARCHS=arm64) did NOT help.
