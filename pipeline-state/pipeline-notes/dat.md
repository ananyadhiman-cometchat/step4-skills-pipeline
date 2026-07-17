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
