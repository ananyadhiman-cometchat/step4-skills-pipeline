# Consolidated CometChat Gaps — UC1–UC5

> Genuine CometChat **skills / MCP-docs / SDK** gaps found building the Step-4 use cases, consolidated by
> **theme** (not by use case) so recurrence is visible. Recurrence = fix priority: a gap that hits N use
> cases is worth fixing in the skill/SDK before a one-off. Source of truth: `pipeline-state/gaps/<slug>.md`
> (56 marker-tagged findings: mkt 7 · com 16 · del 11 · dat 8 · fin 14). Codegen/harness misses and retracted
> items are excluded — those live in `pipeline-state/pipeline-notes/`.
>
> UCs: **mkt** = Marketplace (React / RN · Python) · **com** = Community forum (Flutter v6 · PHP) ·
> **del** = Delivery (Angular / Android-Compose-v6 / iOS-Swift · Node) · **dat** = Dating (React / RN · Python) ·
> **fin** = Fintech support (Vue 3 · Android-Compose-v6 / iOS-Swift · Java-Spring).

## Ranked by impact × recurrence (fix these first)

| # | Gap (theme) | UCs hit | Type | § |
|--:|---|:--:|---|:--:|
| 1 | Runtime creds not injected → backend mints **empty auth token** → conversation list "Oops" | **5** · mkt com del dat **fin** | missedTrigger | A1 |
| 2 | Prebuilt **call surfaces don't self-position** — ring/ongoing render off-flow or 0-height (calc-var → 0px) | **4** · mkt del dat **fin** | SDK-gap | C1 |
| 3 | **iOS in-call UI hard-crashes** (RN-bridge SIGSEGV) on `CometChatCallsSDK 4.2.3` / iOS 26 → pin `~> 5.0` | **2 rec · del fin · affects every native-iOS UC** | SDK-gap | C7 |
| 4 | **Virtual devices ring but never connect media** — calls only truly verify on 2 real devices | **3** · com del dat | coverageGap | C4 |
| 5 | REST create-user duplicate = **HTTP 400 `ERR_UID_ALREADY_EXISTS`**, not 409 | **3** · com del **fin** | staleness | A3 |
| 6 | SDK **ships broken/un-consumable artifacts** — RN UIKit uncompiled `.tsx`; iOS xcframeworks + companion sub-modules | **3** · mkt del **fin** | SDK-gap | D1 |
| 7 | iOS **companion modules** (`CometChatStarscream`/`CometChatCardsSwift`) referenced but not vended | **2** · del **fin** (+telehealth/edtech) | SDK-gap | D2 |
| 8 | Calling is a **silent no-op** until hidden prerequisites (init/enableCalls/navKey/perms) are wired | **2** · com dat | coverageGap | C2 |
| 9 | **Placeholder/empty appId fails silently** (dials a dead host) instead of erroring | **2** · mkt dat | missedTrigger | A2 |
| 10 | Web **message list won't scroll** without an app-provided bounded-height wrapper | **2** · mkt dat | missedTrigger | E1 |
| 11 | **Incoming-call overlay intercepts touches app-wide** (whole screen dead behind a toast) | **2** · del dat | SDK-gap | C3 |
| 12 | RN **release build** needs cleartext + INTERNET in the MAIN manifest + iOS ATS | **2** · com dat | missedTrigger | F1 |
| 13 | **iOS in-app incoming call unusable OOTB** — kit's `CometChatIncomingCall` renders **empty** on iOS 26; socket not auto-established after login (offline → no incoming); header shows no call buttons; scaffolded Podfile omits the CallsSDK pod | 1 · **fin** · affects native-iOS | SDK-gap | C8 |
| 14 | **Web logout doesn't clear the SDK session** → account switch shows the **previous user's** chat/contacts | 1 · **fin** | coverageGap | A4 |
| 15 | Flutter **CallButtons + CallNavigationContext unusable with `MaterialApp.router`/go_router** | 1 · com | falseTrigger | C5 |
| 16 | iOS **deployment-target drift**: skills say 13.0, `cometchat_calls_sdk` needs **15.1** | 1 · com | staleness | D3 |
| 17 | RN **UIKit version floor**: `chat-uikit-react-native` needs **RN ≥ 0.76** (breaks Expo SDK 51) | 1 · dat | SDK-gap | D4 |
| 18 | Calls-SDK **lifecycle traps**: eager init hijacks incoming · async `getLoggedInUser()` guard no-op · `joinSession` needs explicit login · incoming event carries only uid ("Unknown Caller") | 1 · com | SDK-gap/docsEscape | C6 |
| 19 | **Android v6 skill hallucination**: `CometChatIncomingCall` documented without its required `call` param → won't compile | 1 · **fin** | hallucination | G1 |
| 20 | iOS RN Podfile **`use_modular_headers!`** missing (pod deps don't define modules) | 1 · mkt | missedTrigger | F2 |

---

## A. Auth / provisioning

**A1 — Empty auth token → "Oops" (hits 5/5).** The production/deployment skill wires `COMETCHAT_*` into code + `.env.example` but not the **runtime** env (docker-compose/service), so the backend mints an **empty** `cometchat_auth_token` and every client's conversation list errors "Oops". On dat, compounded by login/signup not calling `createUser` before minting (the user 404s → empty token). Recurs on **fin** (Java-Spring backend, same docker-compose runtime-env miss). **Ask:** the deployment recipe must inject creds into the runtime env; the server recipe must `createUser` (idempotent) *before* minting.

**A2 — Placeholder appId fails silently (mkt, dat).** With `your_app_id_here` / an empty `*_COMETCHAT_APP_ID`, the SDK dials a non-existent host, the socket never connects, and nothing surfaces (chat spins forever; calls never arrive). **Ask:** the SDK should **fail loudly** on a placeholder/invalid appId; the integrate recipe must write the real appId into `.env`.

**A3 — Duplicate create-user is 400, not 409 (com, del, fin).** `POST /v3/users` for an existing uid returns **HTTP 400 `{error.code: ERR_UID_ALREADY_EXISTS}`**, but the `cometchat-production` recipe branches on `status === 409`, so idempotent re-provision (re-seed/retry/signup collision) is treated as a hard failure. On **fin** the backend's `CometChatService.isAlreadyExists()` had to accept 409 **OR** 400+`ERR_UID_ALREADY_EXISTS` for re-seed to be idempotent. **Ask:** detect via `error.code === 'ERR_UID_ALREADY_EXISTS'`, not HTTP 409.

**A4 — Web logout doesn't clear the CometChat SDK session → account-switch identity bleed (fin).** The app's own logout (Pinia store) cleared its localStorage tokens but never called `CometChatUIKit.logout()`, and the chat island's login guard returned early whenever *any* user was already logged into the SDK (`getLoggedinUser() != null`). So signing out and signing in as a **different** user in the same browser left the previous user's SDK session live — the new user's conversation list and contacts rendered the **previous** user's data under scrambled names (looked like "I message Alice from Bob and it lands on Carol"). **Ask:** the integration/placement skill must state that app-level logout MUST call the kit's `logout()`, and the login path must **reconcile the SDK session against the intended uid** (log the stale user out, then log the new one in) — a latent bug in any island/embedded integration that logs out via app state instead of the kit.

## C. Calling — placement, lifecycle & testing

**C1 — Call surfaces don't self-position (mkt, del, dat, fin).** Across React (Standard mode), Angular, and the React UI Kit mounted as an island inside Vue (**fin**), the prebuilt `IncomingCall`/`OutgoingCall`/`OngoingCall` render **inline** wherever mounted: the ring appears as a bottom-left banner (callee can't find Accept → "Missed"); the ongoing surface inherits a 0-height/bounded box and the chat bleeds through. Root sub-cause: the calls SDK sizes its tile-grid with `calc(100% − var(--cometchat-calls-call-*-height))` but **never defines those vars** → `0px` → ResizeObserver throws "Container dimensions must be positive" (self-heal `web-call-css-vars` fires on both dat and fin). **Ask:** self-position the call components as a full-viewport modal (or ship the overlay CSS in the Standard-mode docs), and **define the `--cometchat-calls-*` vars** (or use `var(--x, 0px)` fallbacks). *Workaround:* `.cc-call-overlay{position:fixed;inset:0}` + force `.cometchat-ongoing-call` full-viewport + define both vars in `:root`.

**C2 — Calling is a silent no-op until prereqs wired (com, dat).** `CometChatCallButtons` renders and looks functional but tapping does **nothing** — no screen, no error, no disabled state — until hidden prerequisites are in place: Flutter needs `enableCalls=true` + `CometChatUIKitCalls.init` + `navigatorKey`; RN needs an explicit `CometChatCalls.init` after UIKit init. **Ask:** co-locate the init prerequisite with the component; surface a disabled/error state when calling isn't wired.

**C3 — Incoming-call overlay intercepts touches app-wide (del, dat).** The root-mounted `CometChatIncomingCall` overlay hit-tests the **whole screen**, so a lingering/stuck call makes the entire app unusable (worsened by stuck server-side sessions re-delivering on login). **Ask:** hit-test passthrough except the toast, and/or auto-reject stale calls. *Workaround:* `:has()`-gated overlay + `pointer-events:none` when idle.

**C4 — Virtual devices ring but never connect media (com, del, dat).** Signaling works on emulators/simulators (caller "Calling…", callee rings), but the **WebRTC media session never establishes** — calls end "Missed"/"rejected". Audio-only fails too, so it's not arch/camera. The guide says "test on real devices" but never **warns** that virtual devices *falsely* show calling as broken. **Ask:** state that call verification requires **two physical devices**; add a troubleshooting entry.

**C7 — iOS in-call UI hard-crashes on `CometChatCallsSDK 4.2.3` / iOS 26 (del, fin; affects every native-iOS UC).** Placement, ringing, signaling and WebRTC media all work, but the instant the in-call session UI mounts the app dies: `EXC_BAD_ACCESS` (SIGSEGV, "possible pointer authentication failure") inside `CometChatCallsSDK → facebook::react::invokeInner` / `RCTNativeModule::invoke` — the **React Native runtime embedded in the Calls SDK** segfaults during a native-module invoke. Crashes identically on arm64 sim **and** x86_64/Rosetta. **FIX (one line):** pin `pod 'CometChatCallsSDK', '~> 5.0'` (resolves **5.0.1**) instead of `~> 4.1` (→ 4.2.3). Everything else identical — CometChatSDK 4.1.6, CometChatUIKitSwift 5.1.16, WebRTC 124.0.4, the I7 companion pods. No `post_install` RCTBridge hack, no custom-view `startSession(view:)` bypass needed. Verified on the same stack (marketplace + edtech, iOS 26.5 sim); the self-heal `ios-calls-sdk-version` guard confirmed the pin present on **fin** too.
**Honesty:** 5.0.1 **still embeds React Native** (RCTBridge present, ~2376 RN symbols) — this is *not* "5.x removed RN". The claim is strictly **empirical**: the 5.0.1 RN build doesn't trip the PAC/unwinder fault on iOS 26; 4.2.3 does (which also kills "iOS 26 PAC" as a general cause — the reference sim is 26.5). **Ask:** fix 4.2.3's iOS-26 crash, or document that `~> 5.0` is required for iOS-26 even against the 4.1.x chat SDK. **Codegen must pin `~> 5.0` for every native-iOS UC.** *Watch-outs after the bump:* only the **first** call per launch connects (kit state bug); and a separate SIGSEGV in `CometChatCallBubble.setupStyle` (`CallType.rawValue` on null) when rendering a group-call history bubble.

**C8 — iOS in-app incoming call is unusable out-of-the-box (fin).** Four independent gaps combined so a by-the-book native-iOS integration could neither reliably receive nor place a call — even after C7. (a) **The realtime socket is not auto-established after login:** `CometChatUIKit.init`/login authenticates over REST and fetches conversations, but the websocket that delivers incoming calls + presence stays down, so the device reads OFFLINE and the (registered) call listener never fires — *outgoing* still works because `initiateCall` is REST, which is the tell. Needs `UIKitSettings.autoEstablishSocketConnection(true)` **and** an explicit `CometChat.connect()` after login *and* on the restored-session path (the first connect often returns a transient `WSError 1`, then succeeds). (b) **The kit's `CometChatIncomingCall` renders EMPTY on iOS 26:** presented modally, embedded, via `.fullScreenCover`, or in a dedicated `UIWindow`, it builds (`onAppear`/completion fire) but draws nothing — the call arrives but no ring appears; a custom SwiftUI ring only displays when embedded with proper VC containment (`addChild` + view on `root.view` + `didMove`) — a bare `UIHostingController.view` subview or a `.fullScreenCover` on a `TabView` never runs its SwiftUI render pass. (c) **`CometChatMessageHeader` shows no call buttons** on the explicit-pod setup (un-hiding them does nothing; adding to `tailView` is dropped) — you must mount `CometChatCallButtons().set(user:).set(controller:)` in your own view. (d) **Scaffolded Podfile omits the `CometChatCallsSDK` pod** entirely → the calling UI still renders (looks like it works) but `CometChat.initiateCall` fails at runtime with "Framework not installed" (self-heal `ios-calls-sdk-absent` now ADDs the pod). **Ask:** the iOS calls skill must establish the socket on login, ship a working incoming-call surface for iOS 26 (or document the containment requirement), co-locate the header call-button wiring, and require the CallsSDK pod. *(Still open on fin: an iOS outgoing call rings + shows "Calling…" but the media session never establishes on accept — likely the hand-written `CometChatCalls.init` standalone path missing the `onOutgoingCallAccepted → generateToken → startSession` sequence.)*

**C5 — CallButtons + `CallNavigationContext` unusable with `MaterialApp.router`/go_router (com).** The kit presents the outgoing call via `Navigator.push(CallNavigationContext.navigatorKey.currentContext, …)`; that key is never owned by go_router, so the button silently no-ops. **Ask:** WARN that this combo (the de-facto Flutter routing standard) is a silent no-op, and ship the **raw-`cometchat_calls_sdk` + `rootNavigator:true` + explicit `CometChatCalls.loginWithAuthToken`** recipe as the supported path.

**C6 — Calls-SDK lifecycle traps (com).** (a) Eager `CometChatUIKitCalls.init` at startup registers native telecom handlers that **hijack incoming calls and background/close** the app → init lazily on the call path when you own the incoming UI. (b) `CometChatCalls.getLoggedInUser()` returns a **`Future`**, so `if (getLoggedInUser() != null)` is always true → the required Calls login is skipped → `joinSession` fails `ERROR_AUTH_TOKEN`. (c) The Join-Session quick-start documents **no login prerequisite**. (d) The incoming-call event carries **only the caller uid** → rings as "Unknown Caller" unless resolved via `getUser`. **Ask:** document the async return, the explicit calls-login, and the name resolution; consider a sync `isLoggedIn`.

## D. SDK packaging & docs/version drift

**D1 — Ships broken artifacts (mkt, del, fin).** RN UIKit ships **uncompiled `.tsx` with its own TS errors** (strict `tsc` fails on the library). iOS `CometChatUIKitSwift`/`CometChatSDK` xcframeworks ship a `.swiftinterface` importing **merged-but-unvended sub-modules** → un-consumable via CocoaPods+simulator on any compiler. On **fin** the same family surfaced two more I7 modes: the `generic/platform=iOS Simulator` destination builds an **x86_64** slice that can't resolve `CometChatCardsSwift` (needs `EXCLUDED_ARCHS=x86_64`), and an **empty-stub** `CometChatStarscream` links but crashes at launch (`Symbol not found: WebSocketEvent`). **Ask:** ship compiled `.d.ts`; ship consumable sub-module interfaces / vend the sub-frameworks.

**D2 — iOS companion modules referenced but not vended (del, fin; also telehealth/edtech).** `CometChatSDK` imports `CometChatStarscream`, `CometChatUIKitSwift` imports `CometChatCardsSwift`, but the default pods reference them **without bundling/declaring** → `no such module`. Recurred on **fin** (self-heal `ios-companion-pods`). **Fix (proven):** add both explicitly via CocoaPods (`CometChatStarscream` 1.0.2 via a local podspec off CometChat's CDN; `CometChatCardsSwift ~> 1.1`) — NOT SPM (empty stubs link but crash at launch). **Ask:** pods should pull companions transitively.

**D3 — iOS deployment-target drift (com).** Skills assert iOS **13.0** in ≥6 places, but `cometchat_calls_sdk` 5.0.3's podspec is **15.1** (pulled transitively by v6 chat-uikit → applies to *every* v6 app). At 13.0, `pod install` fails. **Ask:** state the true **15.1** floor.

**D4 — RN UIKit version floor (dat).** `@cometchat/chat-uikit-react-native@5.3.10` pulls `cards-react-native@1.0.0` with a hard `peer react-native ">=0.76.0"`; on Expo SDK 51 (RN 0.74.5) install ERESOLVEs and the iOS build fails. **Ask:** state the **RN floor per UIKit version**; codegen must scaffold a compatible RN.

## E. Web layout

**E1 — Message list won't scroll (mkt, dat).** The kit injects a `.cometchat` wrapper that grows unbounded unless the host bounds its height. **Ask:** ship the bounded-height wrapper in the mount recipe. *Workaround:* `.cc-msg-list > .cometchat{height:100%;min-height:0;overflow:hidden}`.

## F. Mobile native setup

**F1 — Release cleartext + INTERNET (com, dat).** A RELEASE build against a local HTTP backend needs `usesCleartextTraffic` + network-security-config **AND** `INTERNET` in the **MAIN** manifest (injected only into DEBUG by default) + iOS ATS. **Ask:** document these together.

**F2 — iOS RN Podfile `use_modular_headers!` (mkt).** The Swift RN UI-kit pod fails `pod install` because deps don't define modules. **Ask:** add it via a config plugin that survives `expo prebuild`.

## G. Skill documentation errors

**G1 — Android v6 skill documents a `CometChatIncomingCall` signature that won't compile (fin).** `cometchat-android-v6-calls` documents the Compose incoming-call component as `CometChatIncomingCall(modifier)` / `CometChatIncomingCall()`, but the actual component (chatuikit-compose-android 6.0.3) requires the `Call` as its first, **non-defaulted** parameter → `error: No value passed for parameter 'call'`. The app must own the incoming-call state and pass the live `Call`. **Ask:** correct the skill's signature and show the app-owns-the-`Call` pattern (mount the overlay only while a call is actually ringing).

---

## Scope notes
- **Codegen misses** (agent wrote wrong code against a *correct* skill) and **harness/env** issues live in `pipeline-state/pipeline-notes/<slug>.md`, not here.
- **Retracted** items (checked → not a real CometChat gap) are marked in the per-UC files and not counted.
- Tally + lint: `pipeline/lib/gaps.py` (`rebuild()` / `lint()`); rollup: `MASTER_GAPS.md`.
