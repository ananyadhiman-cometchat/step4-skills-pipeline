# dat — harness/setup notes (self-heal witnessed)

## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)
<!-- selfheal:expo-android-splash-color -->
- **`note:`** [self-heal:expo-android-splash-color] RN/Expo prebuild references @color/splashscreen_background in splashscreen.xml but omits it from colors.xml → release assembleRelease resource-linking fails; define the color (codegen gap).
  - _auto-repaired by the harness (fix's existence IS the finding)_: defined splashscreen_background in android colors.xml
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`


## Manual harness notes (mobile demo screenshots)
<!-- note:ios-demo-destination -->
- **[harness] iOS demo build had no `-destination`.** `mobile.build_ios` invoked `xcodebuild -workspace
  dat.xcworkspace -scheme dat -sdk iphonesimulator ... clean build` with NO `-destination`, so on Xcode
  16/26 xcodebuild aborts *"Found no destinations for the scheme 'dat' and action clean"* before building —
  the RN iOS demo screenshot never captured (scheme exists + is shared, pods installed; the app itself is
  fine — this is a demo-screenshot-only harness gap, does NOT affect the shipped app or the CP1 baseline).
  FIX applied: add `-destination 'generic/platform=iOS Simulator'` (needs no booted sim). **VERIFIED
  end-to-end 2026-07-17**: with the destination, `build_ios` → exit 0, .app produced, installed on the
  iPhone 17 sim and screenshotted (login screen renders). NOTE the build needs
  `DEVELOPER_DIR=/Applications/Xcode-26.2.0.app/Contents/Developer` (the default /Applications/Xcode.app
  targets an iOS SDK that isn't installed) and the only available sim here is **iPhone 17**, while
  `mobile.install_launch_shot_ios` defaults to `device="iPhone 16"` → the harness default is stale and will
  miss the sim on this machine; pass/resolve the device dynamically.
<!-- note:ios-logo-missing-glyph -->
- **[app/cosmetic] iOS renders the login logo as a missing-glyph "?" box** (Android renders it fine as
  hearts). Same RN bundle both platforms, so this is an iOS font/asset-resolution gap in the generated app,
  not a build failure. Minor/cosmetic — recorded for the codegen to emit an asset-backed logo instead of a
  glyph that can tofu on iOS.
<!-- note:emoji-as-icons -->
- **[codegen] Raw EMOJI used as UI icons → all icons tofu on iOS.** The generated RN app used emoji
  characters as icons (tab bar `🔍 💞 👤 🛡 ⚖️`, `❤️ Like` buttons, `💞` logo, `🌸/✅` empty states,
  `⛔/🗑/⏸` actions). Emoji need a platform emoji font: on the iOS sim EVERY one rendered as a
  missing-glyph "?" box (`❤️` = U+2764+U+FE0F tofu'd as TWO boxes), while Android's font fallback hid it
  entirely — so a web+Android-only check would have shipped this. Bonus bug: `tabBarIcon: () =>` ignored
  the `color` param, so emoji tabs could never show the active/inactive tint.
  FIX: swapped all icon emoji → `@expo/vector-icons` Ionicons (ships with Expo, no new dep; renders from
  its own bundled font on both platforms and honours `color`). DEPTH STANDARD §D now forbids emoji-as-icons
  so future use cases can't regress. User found this by tapping the sim — the harness cannot auto-tap iOS.
<!-- note:docker-vm-network-wedged -->
- **[infra] verify halted: Docker VM networking wedged → base-image metadata timeout.** `verify` failed with
  `GATE-FAIL[infra]: integrated system did not boot healthy (backend=False web=False)`. Real cause was NOT
  the app: `docker compose up -d --build` died at
  `[backend internal] load metadata for docker.io/library/python:3.12-slim → DeadlineExceeded: context
  deadline exceeded`. Evidence it's the Docker VM, not the network: the HOST reached Docker Hub fine
  (`auth.docker.io` 200 in 0.25s, `registry-1.docker.io` 401 in 0.6s) while the daemon's own
  `docker pull python:3.12-slim` hung indefinitely. A stale `com.docker.backend` was lingering — the SAME
  failure mode seen earlier this project. FIX: quit Docker, `pkill -9 -f com.docker.backend` + helpers,
  `open -a Docker`, wait for `docker info`, re-run verify.
  Two harness gaps this exposed:
  1. **Misleading gate message.** `backend=False web=False` reads like the health checks failed, but they
     never RAN — they are gated on `dockerUp` (`health_check(...) if dockerUp else (False, None)`), so a
     dead `compose_up` reports as two dead health checks. The stale baseline containers were still Up and
     answering 200 the whole time, so nothing about the INTEGRATED app was tested. The gate should
     distinguish "compose_up failed" from "booted but unhealthy" and surface `boot_tail` (HALT.json's
     `gate_output` was empty).
  2. **`--pull=false` retry can't fix a missing base image.** `compose_up` already retries on the
     `DeadlineExceeded|context deadline exceeded` signature with `docker compose build --pull=false`, but
     that only skips pulling a NEWER base — BuildKit still resolves registry metadata, and here
     `python:3.12-slim` was not even cached locally (pruned; only the derived `dat-backend:latest` and
     `nginx:alpine`/`node:20-alpine` survived). So the retry was structurally incapable of rescuing this.
     A real retry needs daemon-health/DNS detection (or a warm base-image cache the disk self-heal won't prune).

### auto-recorded verify triage (dat)
- [harness] cross-party chat proof did not run cleanly — {'aLogin': False, 'bLogin': False, 'aOpened': False, 'bOpened': False, 'sent': False, 'received': False, 'senderEcho': False, 'error': 'TimeoutError: page.waitForFunction: Timeout 20000ms exceeded.', 'chatWorks': False}
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': False, 'calleeLogin': False, 'callerCallStarted': False, 'calleeRingVisible': False, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': False, 'callerOngoing': False, 'calleeOngoing': False, 'c
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)

### auto-recorded verify triage (dat)
- [harness] cross-party chat proof did not run cleanly — {'aLogin': False, 'bLogin': False, 'aOpened': False, 'bOpened': False, 'sent': False, 'received': False, 'senderEcho': False, 'error': 'TimeoutError: page.waitForFunction: Timeout 20000ms exceeded.', 'chatWorks': False}
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': False, 'calleeLogin': False, 'callerCallStarted': False, 'calleeRingVisible': False, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': False, 'callerOngoing': False, 'calleeOngoing': False, 'c
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
<!-- note:web-buildtime-creds-and-seed-pw -->
- **[harness] verify chat proof failed on TWO cred/auth gaps (both fixed):**
  1. **Web build-time CometChat creds empty.** `web/.env` shipped `VITE_COMETCHAT_APP_ID=` (empty). Vite
     inlines `import.meta.env.VITE_*` at build, so the bundle had a blank appId → `init.ts` threw "Missing
     VITE_COMETCHAT_APP_ID" → SDK never inits. provision writes `.env.cometchat` + compose-env feeds the
     BACKEND, but nothing filled the WEB build-time cred. FIX: new self-heal `web-cometchat-creds` (pre,
     family web, when_integrated, owner harness) fills any empty/placeholder VITE_/NEXT_PUBLIC_/REACT_APP_
     *_COMETCHAT_{APP_ID,REGION,AUTH_KEY} the web .env declares, from the provisioned env; wired into verify
     before `compose_up --build`. Verified: real 17-char appId baked into the served bundle.
  2. **Seed-password drift (same class as del/iOS).** dat's spec + backend + web/mobile quick-fill all use
     `Seed1234!`, but the harness `e2e_password()` derives `Dat@seed2026!` → every seeded login 401'd → the
     browser proof timed out on `waitForFunction(leave /login)` → mislabeled `sdk=False`. The requirements
     TEMPLATE said only "password = the shared seed password" without pinning the literal, so codegen chose
     `Seed1234!`. FIX (two parts): (a) dat gets `"e2ePassword": "Seed1234!"` in use_cases.json so the harness
     matches the built app; (b) the template now PINS the exact literal `{Slug}@seed2026!` (added `Slug` fmt
     key) so future codegen matches `e2e_password`'s default and this drift can't recur.
  Note the misleading verdict: a login/seed 401 surfaces as `sdk=False chatRx=False` because the proof never
  gets past login to touch the SDK — the harness should distinguish "login failed" from "SDK init failed".

### auto-recorded verify triage (dat)
- [integration] cross-party message NOT received (real-time socket) — [{'received': False, 'error': None}, {'received': False, 'error': None}]
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [env] web CALL screens unrenderable headless — two-party WebRTC media can't be negotiated in an automated browser (caller stuck at 'Calling…', callee blank): callee-ringing-voice(not_corner_toast,accept_reject,caller_shown), callee-ongoing-voice(fullscreen,no_app_chrome,no_chat_bleed,controls), callee-ringing-video(not_corner_toast,accept_reject,caller_shown), callee-ongoing-video(fullscreen,no_app_chrome,no_chat_bleed,controls). Call CONNECTION proven by machine evidence (callConnect/twoParty) + native↔native live matrix; these shots are ADVISORY. See gallery /Users/admin/Desktop/automate/runs/dat/_demo/shot-review.html
<!-- note:proof-composer-selector -->
- **[harness] cross-party chat proof missed the compact composer.** After the cred + password fixes, the
  proof got `aOpened/bOpened=true` but `sent=false` → `chatReceive=false`. dat's web uses
  `CometChatCompactMessageComposer` (valid UIKit component), whose input is a contenteditable DIV
  `cometchat-compact-message-composer__input` — the proof's selector only matched
  `.cometchat-message-composer*` (no "compact"), so it never found the input to type into. FIX: broadened
  the composer-input selector in `e2e/twoparty_chat.web.mjs` to span every variant
  (`[class*="composer" i] [contenteditable], [class*="composer" i][contenteditable], … __input`). Verified
  manually: sent=true, **received=true** (A got B's nonce over the live socket) → chatWorks=true. dat's
  CometChat real-time chat genuinely works; the gap was purely in the test's selector breadth.

### auto-recorded verify triage (dat)
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [env] web CALL screens unrenderable headless — two-party WebRTC media can't be negotiated in an automated browser (caller stuck at 'Calling…', callee blank): callee-ringing-voice(not_corner_toast,accept_reject,caller_shown), callee-ongoing-voice(fullscreen,no_app_chrome,no_chat_bleed,controls), callee-ringing-video(not_corner_toast,accept_reject,caller_shown), callee-ongoing-video(fullscreen,no_app_chrome). Call CONNECTION proven by machine evidence (callConnect/twoParty) + native↔native live matrix; these shots are ADVISORY. See gallery /Users/admin/Desktop/automate/runs/dat/_demo/shot-review.html
<!-- note:rn-ios-integrated-build-chain -->
- **[harness/codegen] Integrated RN iOS build needed a chain of native fixes** (found while capturing the
  icon-fix screenshot). In order: (1) `ios/` had no Podfile/xcworkspace after integrate → needs `expo
  prebuild -p ios`; (2) deployment target 13.4 too low for netinfo/CometChat → bumped
  `Podfile.properties.json` `ios.deploymentTarget=16.0`; (3) Swift CometChat pods can't be static libs →
  `pod-modular` self-heal (`:modular_headers => true` for SPTPersistentCache/DVAssetLoaderDelegate); (4)
  **`build_ios` bug**: it globbed `*.xcworkspace` at function ENTRY, before its own `pod install` creates it,
  so a freshly-prebuilt project fell back to scheme "Marketplace" → `'Marketplace.xcworkspace' does not
  exist`. FIXED: derive the scheme from the always-present `*.xcodeproj` when no workspace exists yet. (5)
  Then the hard stop: the CometChat-RN-version incompat above (see gaps/dat.md) — not fixable without a
  version-alignment decision. NOTE (1)-(3) get wiped by `expo prebuild` (CNG) — the durable form is an
  expo config plugin, not a post-prebuild edit.
<!-- note:demo-users-not-cometchat-provisioned -->
- **[integration] App demo accounts are NOT provisioned as CometChat users → mobile chat spins forever.**
  Runtime-validating dat mobile: logging in via the Member/Admin/Guest demo quick-fill, the Chat tab's
  CometChat Conversations list spins indefinitely. Cause: `dat-mem-001` (member1@dat.io) returns HTTP 404
  from the CometChat REST API — the CometChat app only has the 5 defaults + the chat-test pair
  (dat-cha-001/dat-chb-001) + 2 mod-probes (9 users total). The backend seed creates demo users in its OWN
  DB but never creates them as CometChat users, so `CometChatUIKit.login({authToken})` fails silently (the
  provider only console.warns) and the conversation list never resolves. This means EVERY real demo login
  (except the two chat-test users) has broken chat. FIX: the backend must create the CometChat user (REST
  createUser, idempotent) on signup/seed for every app user, then mint the auth token — OR the seed must
  provision all demo accounts into CometChat. verify doesn't catch this because it logs in as the chat-test
  pair (which IS provisioned) — the web proof uses the same two users. Genuine coverage + integration gap.
<!-- note:mobile-cometchat-VALIDATED -->
- **[VALIDATED] dat mobile CometChat chat + calls work at runtime (Android, SDK 52 / RN 0.76.9).** Logged
  the debug app in as chat-a@dat.io (a provisioned CometChat user) → CometChat login succeeded
  ("CometChatCalls initialization completed successfully"), the Conversations list loaded the real Chat-B
  thread from the cloud (full history incl. the web-verify nonces + inline voice/video CALL-event bubbles),
  and a FRESH message REST-sent as chat-b (live-rx-<ts>) arrived LIVE in the open thread. So SDK init +
  login + conversation list + message history sync + REAL-TIME receive + the composer + call buttons all
  work on device. Only prerequisite: the user must be a provisioned CometChat user (see the demo-users gap
  above — Member/Admin/Guest 404 and spin; chat-a/chat-b work). iOS builds+launches (login screen) but the
  harness can't tap iOS to drive the same flow; the shared RN bundle behaves identically.
<!-- note:FALSE-POSITIVE-chat-and-calls -->
- **[HARNESS false-positive — the important one] verify reported chat GREEN while EVERY real user's chat was
  broken.** Root app bug: backend `login` minted a CometChat token via cc_auth_token but never cc_create_user
  first (only signup did) → seeded/demo accounts (member1, admin, …) 404 in CometChat → empty token →
  CometChatUIKit.login fails → chat page never loads (web + iOS + android). Why verify missed it:
  `seed_and_resolve_pair` PROVISIONS the chat-test pair in CometChat OUT-OF-BAND (create_user), doing what
  the app's login should do — so the proof passed on a rigged pair while real users were broken; and
  `app_login` discarded the cometchat_auth_token so verify never checked it. FIXES: (1) backend
  `_auth_response` now cc_create_user before minting (app fix, verified: member1 web chat opens); (2)
  app_login now captures cometchat_auth_token and verify GATES on it being non-empty for the demo pair
  (tag=skills) — would have caught this; (3) integrate.md.tmpl now mandates login-provisions-user. Calls were
  ALSO broken (CometChatCalls.init never called → header buttons inert) + a login red-box crash
  (Alert.alert given FastAPI's array `detail`) — both fixed. NOTE: live CALL connection is still NOT verified
  end-to-end (WebRTC + two devices can't be automated headless) — the setup gaps are fixed but a real call
  connecting remains unproven; do not report calling as working without a manual two-device test.
<!-- note:calls-actually-verified + regression-answer -->
- **[HARNESS] "calls unverified" + "false positive recurred" — root causes + fixes.** (1) The rigged-pair
  masking was NEVER fully removed: commit 28c05f0 added a `chatPair` opt-in but only `com` (1/10 UCs) set it;
  dat + 7 others fell back to the legacy `fixed-chat-ab` path that skipped app_login (and the token check).
  FIX: seed_and_resolve_pair now ALWAYS resolves via the app's real login (defaults to chat-a/chat-b@slug.io)
  and captures cometchat_auth_token; verify gates on it being non-empty for EVERY UC (universal now). (2)
  Calls were "verified" by a SIGNALING-only verdict (`callWorks = calleeRingVisible && calleeAccepted`) that
  passed even when the call never connected — AND the accounts weren't provisioned so it never even started.
  With the provisioning fix, running twoparty.web.mjs (which already uses `--use-fake-device-for-media-stream`)
  shows the call CONNECTS: callerOngoing=true, calleeOngoing=true, real ongoing-call UI on both ends
  (screenshots callee/caller-ongoing-voice.png). FIX: callWorks now REQUIRES connectOk (both ends ongoing) +
  server-answered — deterministic connect teeth. The "headless can't do WebRTC / can't render the call"
  claim was FALSE (fake-media Chromium does it); the real blocker was always the un-provisioned users.
<!-- note:match-peer-not-provisioned -->
- **[integration] Chatting with a MATCH errors ("Oops") — the match's user isn't in CometChat.** Found via
  real-device QA: on android, opening the chat with a match (Riley Park / dat-mem-002) shows CometChat's
  "Oops! Looks like something went wrong" message-list error. dat-mem-002 → REST 404. Cause: my login-time
  provisioning fix creates the CometChat user for whoever LOGS IN, but a match/peer you chat with must ALSO
  exist in CometChat — and seeded profile owners who never logged in don't. So 1:1 chat only works between
  two users who have each logged in at least once. FIX (follow-up): the backend seed must createUser in
  CometChat for EVERY seeded user (idempotent), OR match-creation must provision both parties. Same
  provisioning root as [[verify-rigged-pair-masks-broken-chat]] but on the PEER side. Note the Conversations
  list itself loads fine (empty state) — only opening a thread with an unprovisioned peer errors.

### [harness] Verify/demo must exercise the REAL match→chat entry point, not a pre-seeded pair
dat's MatchDetailPage shipped a `Chat panel — powered by CometChat (coming soon)` STUB — the entry point every
real user hits (open a match → chat) was a dead end — yet verify passed because it drove `/conversations` with an
out-of-band pre-seeded pair that already had a thread. Harden verify to: seed an ACTIVE match between two seeded
members, log in as one, navigate the match route, assert the CometChat thread mounts (composer visible), then
send + cross-receive. Same "all-usecase vs unique-instance" false-positive family as verify-rigged-pair. App fix
committed d90121d8 (embed real MessageHeader+List+Composer in MatchDetailPage).

### [harness] RN mobile call verification — automation + build reality
1) `adb shell input tap` CANNOT drive the CometChat RN MessageHeader touchables (gesture-handler); tapping the
   header call button no-ops with zero JS logs → looks like "call button broken" but is an automation artifact.
   Drive via Maestro (`tapOn: {point}`) OR prove calls from the RECEIVE side (web peer rings the device via
   Playwright/fake-media → `adb` taps the incoming-call Accept, which IS a standard touchable → OngoingCall connects).
2) The RN debug app keeps the Metro bundle it loaded at launch IN MEMORY; a committed JS fix (e.g. CometChatCalls.init)
   is not live until force-stop+relaunch or an APK rebuild — the built demo APK can lag the committed source and read
   as "still broken". Rebuild the APK (or reload) before judging mobile.
3) `CometChatCallButtons.makeVoiceCall` silently returns (no log, no call) if RECORD_AUDIO/CAMERA isn't granted —
   pre-grant on the emulator before the call check.

### [deliverable] Green-light proof gallery standard
Finalized a per-usecase "green light" screenshot gallery (Artifact) organized by platform (Web/Android/iOS) with
per-shot status pills (Verified / Open issue) and a one-line "what it proves" caption — honest about partial
platforms rather than all-green. Builder: runs/dat/_shots/build_gallery.py (sips-resize → base64-embed → Artifact).
This is the format to reuse as the pipeline's green-light standard the user asked to finalize.

### [codegen/app] RN screens generated WITHOUT safe-area insets → header buttons dead (call/video/logout)
User manual-QA: "can't click the upper buttons (call, video, logout) in BOTH mobile apps." Root cause: generated RN
screens had no safe-area handling — ChatScreen/ConversationsScreen used a bare top View, and the other 8 screens
imported `SafeAreaView` from **'react-native'** (a no-op on Android). So the whole top strip (CometChat MessageHeader
back+voice+video buttons; each screen's title + Log Out) rendered UNDER the status bar/notch = a dead touch zone.
Visible tell: the app title overlapped the status-bar clock. NOT a gesture-handler/automation issue (I misdiagnosed it
as one first — but the user's finger couldn't tap them either). Fix (commit 6cc01b37): chat screens pad by
`useSafeAreaInsets().top`; other screens import SafeAreaView from **'react-native-safe-area-context'**. After the fix
the Android header voice-call button initiates a call. Codegen guidance for RN: NEVER import SafeAreaView from
'react-native' (iOS-only); use react-native-safe-area-context on every screen with a top bar, and give CometChat
message-header screens an explicit top inset. Worth a spec-depth / RN-scaffold check so future RN use cases ship it.
