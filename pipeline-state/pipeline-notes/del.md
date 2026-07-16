# del — harness/environment notes (NOT CometChat gaps)

## Baseline android build failed on toolchain env, not code (2026-07-15, first durable-harness run)
The build stage HALTED because android (Compose) wouldn't compile — two chained environment issues,
both now self-healed; backend/web/iOS compiled first try.

1. **JDK too new.** Machine default is Java 26; Kotlin (AGP 8.7.3 / Gradle 8.11.1) throws
   `IllegalArgumentException: 26.0.1` from `JavaVersion.parse`. A compatible JDK existed (brew
   `openjdk@17`, Android Studio JBR 21) but wasn't default. Harness gap: the `jdk17` self-heal sig
   didn't match the `JavaVersion.parse` signature so it never fired. FIXED: extended sig; `_fix_jdk17`
   discovers a real 17-21 JDK and persists `org.gradle.java.home`. (Also: preflight checks java EXISTS,
   not that its VERSION is android-compatible.)
2. **Android SDK unset.** After the JDK fix: `SDK location not found`. Codegen omits machine-specific
   `local.properties`. Harness gap: no rule. FIXED: added `android-sdk` rule (writes `sdk.dir`).
3. **Diagnose no-HEAD crash.** Build failing before the baseline commit → no HEAD → `git worktree add …
   HEAD` failed. FIXED: `diagnose.py` makes a wip snapshot commit first.

Net: all three are harness/environment robustness fixes; none is a CometChat gap. Protects the remaining
android use cases (fin, evt, cre, rea).

## containerize template .format() KeyError (harness bug)
`render_containerize` did `containerize.md.tmpl.format(...)` but the template embedded a literal nginx
block `location /api/ { proxy_pass http://backend:8000; }` — Python `.format()` read `{ proxy_pass … }`
as a placeholder → `KeyError: ' proxy_pass http'`, crashing every web+backend use case's containerize
stage. FIXED: escaped the literal braces as `{{ }}`. (Real placeholders {backend}/{web}/… unaffected.)

## boot smoke hit the dev port, not the composed web (harness bug)
Codegen correctly parameterised the Playwright baseURL (`process.env.E2E_BASE_URL ?? 'http://localhost:4200'`),
but `verify.run_e2e` never set `E2E_BASE_URL`, so the boot login-smoke navigated to the Angular DEV port
4200 (nothing there) instead of the composed web on 3000 → `loginSmokePassed=False`. FIXED: run_e2e now
sets `E2E_BASE_URL`/`PLAYWRIGHT_BASE_URL`/`BASE_URL` to the deployed web url (default localhost:3000; boot
passes `web_url`). (Separately: the Docker daemon crashed on a buildkit I/O error — infra, user restarted it.)

## demo launch-check used a stale hardcoded package (com.mkt.mobile) — false "app not showing"
The native android/iOS demo providers called install_launch_shot_{android,ios} without the app id, so it
defaulted to mkt's `com.mkt.mobile`: it INSTALLED the real apk (com.del.delivery) but LAUNCHED com.mkt.mobile
→ foreground was the launcher → false "app not showing (crash?)" + a splash-icon screenshot the vision judge
flagged. FIXED: derive the real package from the built artifact — `_apk_package` (aapt dump badging) for
android, `_app_bundle_id` (Info.plist CFBundleIdentifier) for iOS; defaults are None. Re-verified: del's
android app launches (foreground=com.del.delivery/.MainActivity) and renders the real Delivery login UI
(truck branding + Email/Password + Sign In + Demo Accounts). The app was healthy all along.

## codegen-quality: dispatch detail omitted the recipient (customer) + returned raw uids
Product observation (caught by manual inspection at CP1): the parcel/dispatch detail view showed the
courier but NOT the customer — the whole point of a dispatch screen is who it's going to. Root cause was
codegen-quality, not schema: `parcels.customer_uid` is NOT NULL and populated, but (1) the parcels API
did `SELECT *` with NO user joins, so it returned raw uids and no names, and (2) the detail UIs (web +
android) rendered the courier uid but never rendered the customer at all. Fix: API LEFT JOINs users for
customer_name/courier_name/dispatcher_name; web + android show a Customer row (resolved name). Pattern to
watch for in generated apps: detail views that skip key relational fields, and list/detail queries that
return foreign-key ids without resolving display names. Not a CometChat gap.

## demo never logs in on mobile — a real behavioral-verify gap (Issue A), + the iOS bug it hid
User caught this at CP1. The demo's mobile check (install_launch_shot_{android,ios}) only does
install → launch → screenshot, and the vision judge uses the `app_alive` rubric ("is it rendered").
It NEVER types credentials or logs in. So it captured the login SCREEN and called it alive — and never
exercised the authenticated flow.

- A Maestro login flow EXISTS (e2e/mobile_flows/login_shot.flow.yaml: taps a demo button → submits →
  waits for the logged-in home) but is UNUSED by the demo, AND `maestro` is not installed. readiness.py
  checks toolchains but not `maestro`, so the login flow could never run anyway.
- This is exactly review Issue A (gates verify render, not behavior) + Issue B (harness not provisioned).
- The bug it hid (codegen): iOS login CRASHED — `safeUser` (login self projection) omitted `email`, so the
  strict iOS Codable User decode failed ("the data couldn't be read because it is missing"); Android's
  non-null email was silently null. Fixed backend to include email in the login user (self only).

Fix direction for the harness: install maestro (+ a readiness check for it), and have the behavioral-verify
tier RUN the login flow per platform (record pass/fail), not just screenshot the login screen.

## FIX wired: mobile login is now a gating behavioral check (Part-1 durable fix)
Root causes the demo login check didn't run/gate: (1) it was gated behind the launch-check `ok`, which
false-failed on the stale package (fixed by artifact-derived package/bundle); (2) maestro wasn't actually
installed though bootstrap.maestro_install was configured; (3) the login result was recorded but NEVER
gated. Fixes: readiness now REQUIRES `maestro` for android/ios/mobile/app (fails fast if absent); the demo
now DIE-GATES when a launched mobile client can't sign in (login_and_shot via login_shot.flow.yaml —
tap demo button → submit → wait for logged-in home). Verified live on del/iOS: the flow logged in and
reached "Track My Delivery" (the same iOS decode crash would now HALT the demo at baseline, not reach a
human at CP1). NOTE: maestro runs under Java 26 with reflective-access warnings (non-fatal); if a future
JDK blocks it, point maestro at the pinned JDK 17.

## Disk filled to 100% mid-integrate → self-heal detected it but had no room to run diagnose (harness bug)
On the push-main→integrate→verify resume, `integrate` halted on a genuine android compile error, but the
diagnose loop then crashed with `OSError: [Errno 28] No space left on device` writing its OWN log
(`runs/del/_logs/diagnose-integrate-3.log`). Root cause was environmental, three chained harness gaps:
1. **Teardown never ran on finished use cases.** `runs/com` (8.1G) and `runs/mkt` (2.7G) — both long
   completed — still held their full build caches (`app/build`, `.dart_tool`, `Pods`, `node_modules`,
   `vendor`). The teardown stage that should GC a finished UC's working dir didn't fire last wave, so
   ~11G of dead build cache accumulated and the volume hit 100% (164 MiB free of 228 GiB).
2. **No disk preflight / no space guard.** Nothing checks free space before build/containerize/integrate,
   so the pipeline walked straight into ENOSPC instead of failing fast with a clear "free N GB" message.
3. **disk-full self-heal ran too late / diagnose logging is not ENOSPC-safe.** The `disk-full` rule fired
   ("self-heal integrate:android → ['disk-full']; retrying") but couldn't reclaim enough, and the diagnose
   worker's very first act — opening a log file for write — died on ENOSPC and took the whole supervisor
   down (`SUPERVISOR_EXIT=1`).

Manual recovery (2026-07-15): freed ~10.7G by deleting only the regenerable caches — com kept ALL source +
`.env.cometchat` creds + `_demo/` proof + `_reports/` (8.1G→44M, re-demoable with pub get/pod install/npm
install, NO re-provision); mkt kept `_demo/_reports` (2.7G→14M). Volume: 164 MiB → 11 GiB free.

Fix direction for the harness: (a) teardown must run reliably on wave-complete AND be idempotently
re-runnable as a GC pass (`supervisor.py gc` that strips regenerable dirs from finished UCs but keeps
creds+proof); (b) a preflight disk-space gate (require e.g. ≥5 GB free before build/containerize/integrate,
else GC-then-retry or halt with a human-readable message); (c) the disk-full self-heal should reclaim FIRST
(prune the exact regenerable dirs above) before any retry, and diagnose logging must degrade gracefully
(fall back to stderr/memory) instead of crashing the supervisor when it can't open a log. None is a
CometChat gap.

## iOS integrate/build gate never ran `pod install` or built the workspace (harness bug — FIXED)
`verify.build_gate('ios', dir)` compiled with `xcodebuild -scheme ios build` on the bare `.xcodeproj`,
never running `pod install` and never targeting the CocoaPods `.xcworkspace`. So the moment integrate adds
a pod (`pod 'CometChatUIKitSwift'`), the gate fails with `no such module 'CometChatUIKitSwift'` — the code
is fine, the module just isn't installed/linked. The demo & providers paths (`mobile.py`, `providers.py`)
already did `pod install` + `-workspace`; the compile gate didn't. FIXED: added `_ios_gate` — when a Podfile
exists it runs `pod install` (idempotent) then `xcodebuild -workspace <ws> -scheme <name>`; else the bare
project. Protects every iOS use case (rea/evt/cre/fin). NOTE: this only gets iOS PAST the module-missing
stage; del's iOS then hit a genuine CometChat SDK toolchain wall (see gaps/del.md — binaries built with
Swift 6.2.3, un-compilable on Xcode 16.4/Swift 6.1.2). Harness follow-up worth considering: distinguish an
**environment/toolchain-incompatible** component (blocked, needs infra/human — e.g. Xcode update) from a
**codegen** failure (diagnosable), so a wave can reach CP2 on the other platforms with the block recorded
instead of halting the whole use case.

## verify marathon: 7 harness/config bugs between "code compiles" and "chat+call proven" (2026-07-16)
After iOS was excluded (CometChat SDK bug) and del reached `verify` on web+android+backend, verify refuted
7 times — EVERY cause was harness/environment/config, NONE was del's app logic (the app works: proven
hands-on that login→dashboard→CometChat conversations render + JitsiMeetJS inits). Fixed in order:
1. **Docker VM networking** — I removed the Docker VM disk earlier to free space for Xcode; the recreated
   VM couldn't pull base images through its internal hub-proxy (`http.docker.internal:3128`). Two restarts
   didn't fix it; a Docker Desktop **factory reset** did. (Lesson: freeing space by deleting the Docker VM
   disk breaks its networking until a factory reset — don't do that; prune images instead.)
3. **`node:20` too old for Angular 22** — web Dockerfile used node:20-alpine, Angular 22 CLI needs Node
   ≥22.22.3. FIXED del's Dockerfile → node:22 (the earlier "bump node:22" fix never reached del's web image).
4. **strict `npm ci` + CometChat Angular peer** — see gaps/del.md; FIXED Dockerfile → `npm ci --legacy-peer-deps`.
5. **e2e login `waitForURL` hangs on SPA** (HARNESS, all 4 web e2e scripts) — the app logs in via Angular
   router pushState (login→/dashboard, no `load` event), so `p.waitForURL(..., {waitUntil:'load'})` timed
   out 15s and the WHOLE chat/call proof refuted (sdk=False chatRx=False) though login+CometChat work.
   FIXED → `p.waitForFunction(() => !/\/login\/?$/.test(location.pathname))`. Protects every web use case.
6. **seed password ≠ e2e_password** (codegen) — del's seed hardcoded `Seed1234!`, but the e2e logs in with
   `e2e_password(uc)` = the canonical `Del@seed2026!` → every e2e login 401'd → silent refute. The
   e2e_password docstring literally warns this. FIXED del seed + demoAccounts → `Del@seed2026!`. Harness
   follow-up: the seed prompt/codegen MUST use e2e_password(uc), never a hardcoded literal.
7. **e2e CometChat selectors stale** (HARNESS) — the UIKit renders `.cometchat-conversation-item` (not
   `.cometchat-conversations__list-item`) and `.cometchat-call-buttons__{voice,video}` (plural, not
   `call-button`). openFirstConversation + the call-button click found 0 → chat/call never ran. FIXED all 4
   e2e scripts (added the current classes + aria-label `button[aria-label="Voice call"]`). Verified LIVE:
   chatWorks=true (cross-party real-time receive) and a voice call ring→accept→ongoing (signalOk=true).
RESULT: chat is fully GREEN in verify (sdk=True chatRx=True vision=True). Only the two-party CALL's strict
server-side "answered" gate remains — see the call-accept finding below.

## OPEN: two-party web call — signaling works, but accept-time session join errors (flaky, 404)
verify's call gate = signalOk (ring+accept) AND CometChat REST logs an `ongoing`/answered action
(`call_answered`). Signaling is proven (ring appears, Accept clicked, sometimes both reach ongoing). BUT
the callee's accept intermittently errors from CometChat's OWN UIKit code: `[IncomingCallService] Error
accepting call` + `[CometChatIncomingCall] Error` + a 404 — so the session doesn't join, no server
`ongoing`, callWorks=False. Not app code (no IncomingCallService in del/web/src — it's the UIKit). Prime
suspect: **`@cometchat/calls-sdk-javascript ^5.0.1` paired with `@cometchat/chat-sdk-javascript ^4.1.12`**
(v5 calls SDK against a v4 chat SDK — the cometchat-*-calls skills note v4→v5 API changes like
getRTCToken→generateToken). Candidate fixes to try: pin calls-sdk to ^4.x (match chat-sdk 4.x), or bump
chat-sdk to 5.x; also possible headless-media session-timing flakiness. NOT yet fixed — a genuine
CometChat calls version-pairing gap (also mirror into gaps/del.md once confirmed).

## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)
<!-- selfheal:disk-full -->
- **`note:`** [self-heal:disk-full] UC1: builds filled the disk and crashed Docker
  - _auto-repaired by the harness (fix's existence IS the finding)_: pruned transients; free=0GB
  - _trigger evidence_: `No space left`


### auto-recorded verify triage (del)
- [harness] cross-party chat proof did not run cleanly — {'aLogin': False, 'bLogin': False, 'aOpened': False, 'bOpened': False, 'sent': False, 'received': False, 'senderEcho': False, 'error': 'TimeoutError: page.waitForURL: Timeout 15000ms exceeded.\n=========================== logs ===========================\nwaiting for navigation to "http://localhost:
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': False, 'calleeLogin': False, 'callerCallStarted': False, 'calleeRingVisible': False, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': False, 'callerOngoing': False, 'calleeOngoing': False, 'c
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)

### auto-recorded verify triage (del)
- [harness] cross-party chat proof did not run cleanly — {'aLogin': False, 'bLogin': False, 'aOpened': False, 'bOpened': False, 'sent': False, 'received': False, 'senderEcho': False, 'error': 'TimeoutError: page.waitForURL: Timeout 15000ms exceeded.\n=========================== logs ===========================\nwaiting for navigation until "load"\n=======
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': False, 'calleeLogin': False, 'callerCallStarted': False, 'calleeRingVisible': False, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': False, 'callerOngoing': False, 'calleeOngoing': False, 'c
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)

### auto-recorded verify triage (del)
- [harness] cross-party chat proof did not run cleanly — {'aLogin': False, 'bLogin': False, 'aOpened': False, 'bOpened': False, 'sent': False, 'received': False, 'senderEcho': False, 'error': 'TimeoutError: page.waitForFunction: Timeout 20000ms exceeded.', 'chatWorks': False}
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': False, 'calleeLogin': False, 'callerCallStarted': False, 'calleeRingVisible': False, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': False, 'callerOngoing': False, 'calleeOngoing': False, 'c
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)

### auto-recorded verify triage (del)
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': True, 'calleeLogin': True, 'callerCallStarted': False, 'calleeRingVisible': False, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': False, 'callerOngoing': False, 'calleeOngoing': False, 'cal
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)

### auto-recorded verify triage (del)
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': True, 'calleeLogin': True, 'callerCallStarted': True, 'calleeRingVisible': True, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': True, 'callerOngoing': False, 'calleeOngoing': False, 'callWo
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [visual] Claude-vision flagged: web-call(fullscreen,no_app_chrome,no_chat_bleed,controls), callee-ringing-voice(not_corner_toast,caller_shown), callee-ongoing-voice(fullscreen,no_app_chrome,no_chat_bleed,controls), callee-ringing-video(not_corner_toast,caller_shown), callee-ongoing-video(fullscreen,no_app_chrome,no_chat_bleed,controls) — see gallery /Users/admin/Desktop/automate/runs/del/_demo/shot-review.html
- [codegen] Angular v5 web calls: the ongoing-call container ("Container dimensions and number of tiles must be positive" Jitsi throw) is sized only by the kit's component-scoped :host styles, which race with CometChatOngoingCall.startCall() in ngAfterViewInit -> container measured 0x0 -> throw -> grid never lays out. Codegen must emit GLOBAL styles.scss rules forcing cometchat-ongoing-call (+ .cometchat-ongoing-call inner div, + cometchat-incoming-call.--ongoing) to full viewport (position:fixed; inset:0; 100vw/100vh) so it's sized on first connect. Applied to del/web (verified geometry). Reusable across all Angular web calls UCs. See memory cometchat-angular-ongoing-call-zero-dimension.
- [test-gap] headless Playwright (--use-fake-device-for-media-stream) CANNOT complete a 2-party WebRTC accept: CometChat.acceptCall errors (+404) and no ongoing-call element renders on caller OR callee. The two-party web-call ongoing state is only confirmable in a real browser (two profiles) or via mock-DOM geometry injection. Explains the incomplete web-web call matrix rows above (callerOngoing/calleeOngoing False).
- [codegen] Web calls: added self-heal rule `web-call-css-vars` (selfheal.py, owner=sdk→gaps ledger) wired into verify.py build_gate(kind=web). The CometChat calls SDK sizes its tile grid with inline height:calc(100% - var(--cometchat-calls-call-footer-height) - var(--cometchat-calls-call-header-height)) but never defines those vars → invalid calc → 0px grid → ResizeObserver throws "Container dimensions and number of tiles must be positive". The guard defines both vars (:root, 60px/80px) in the web app's global stylesheet before build, ONLY when @cometchat/calls-sdk-javascript is a dep. Proven in-page: undefined-var calc→0px, defined→674px. Applied+verified in del/web. Reusable across all web calls UCs.
- [test-gap] The pipeline mobile↔web call test "stops at chat" for TWO reasons, now understood: (1) the web ongoing-call grid was collapsing to 0px (the css-vars bug above — now fixed), and (2) a REAL 2-party WebRTC media connection does NOT establish between the automated peers (headless Playwright caller / Android emulator / in-app Electron browser) — calls RING (signaling + incoming widgets work on web+android+ios) but media drops to "Missed"/"calling…" and never fully connects, so the web CALLER's ongoing-call component rarely mounts headless. The pipeline verdict is already media-independent (mobile incoming widget + Maestro accept + CometChat server-answered), which is the right design; the web ongoing SCREENSHOT is the unreliable part. twoparty_mobile.py DOES capture mobile-incoming/mobile-ongoing shots (android call UI renders). Real-device/real-network verifies the full connected call.
