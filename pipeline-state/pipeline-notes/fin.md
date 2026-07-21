# fin — harness/setup notes (self-heal witnessed)

## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)
<!-- selfheal:android-sdk -->
- **`note:`** [self-heal:android-sdk] android gradle build needs sdk.dir/ANDROID_HOME (codegen omits machine-specific local.properties)
  - _auto-repaired by the harness (fix's existence IS the finding)_: sdk.dir=/Users/admin/Library/Android/sdk
  - _trigger evidence_: `SDK location not found`


## Harness defects found at `build` (fixed in-tree; NOT CometChat skills gaps)
Baseline build first gate-failed `buildExit=65`. All three root causes were harness/toolchain, not
codegen — recorded here (not in `gaps/fin.md`) so the skills ledger stays honest.

<!-- harness:ios-scheme-discovery -->
- **`note:`** [harness] `verify._ios_gate` hardcoded `scheme = d.name`, i.e. it assumed the Xcode scheme
  equals the component DIR (`ios`). Codegen names the project after the app (`FinSupport.xcodeproj` →
  scheme `FinSupport`), so xcodebuild aborted before compiling anything.
  - _trigger evidence_: `does not contain a scheme named "ios"` (exit 65)
  - _fix_: `verify._ios_scheme()` asks `xcodebuild -list -json` for the authoritative schemes and prefers
    dir-name → workspace/project stem → first scheme, with an on-disk stem fallback.
  - _blast radius_: every native-iOS use case (del, fin, cre, rea, evt).

<!-- harness:ios-generic-destination -->
- **`note:`** [harness] iOS builds ran `-sdk iphonesimulator` with NO `-destination`. `mobile.build_ios`
  already knew this was required and passed the generic destination; the compile gate and the native-iOS
  demo provider did not.
  - _trigger evidence_: `Found no destinations for the scheme 'FinSupport' and action build` (exit 70)
  - _fix_: `-destination 'generic/platform=iOS Simulator'` added to `verify._ios_gate` AND
    `providers.IOSNativeProvider.demo` (the latter would have failed the demo stage identically).

<!-- harness:xcode-developer-dir -->
- **`note:`** [harness/setup] `xcode-select` pointed at Xcode 16.4 (only iOS SDK 18.5) while the ONLY
  installed simulator runtime was iOS 26.3 (belonging to the also-installed Xcode 26.2) → zero eligible
  simulator destinations, so iOS could never build regardless of the project.
  - _fix_: `mobile.select_developer_dir()` matches simulator-SDK MAJOR to an available runtime major and
    is pinned once in `run_usecase.augment_path`, so build/integrate/demo/verify all use the same usable
    Xcode instead of trusting `xcode-select` or guessing "newest".

<!-- selfheal:kotlin-optin -->
- **`note:`** [self-heal:kotlin-optin] Compose codegen used `testTagsAsResourceId`
  (`@ExperimentalComposeUiApi`) without `@OptIn` → `compileDebugKotlin` failed. The HARNESS itself
  requires that property (Maestro `id:` targeting), so this is structural on every Compose use case and
  is harness-owned, not a CometChat skills gap.
  - _trigger evidence_: `This API is experimental and is likely to change in the future` (MainActivity.kt:26)
  - _fix_: new `kotlin-optin` self-heal rule (`owner: harness`, deliberately NO `gap` field) appends the
    standard Compose opt-in markers to the module's `kotlinOptions.freeCompilerArgs`.

### auto-recorded verify triage (fin)
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': True, 'calleeLogin': True, 'callerCallStarted': True, 'calleeRingVisible': True, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': True, 'callerOngoing': True, 'calleeOngoing': True, 'callWork
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [env] web CALL screens unrenderable headless — two-party WebRTC media can't be negotiated in an automated browser (caller stuck at 'Calling…', callee blank): web-call(fullscreen,controls), callee-ringing-voice(not_corner_toast), callee-ongoing-voice(fullscreen,no_app_chrome,no_chat_bleed,controls), callee-ringing-video(not_corner_toast), callee-ongoing-video(no_app_chrome). Call CONNECTION proven by machine evidence (callConnect/twoParty) + native↔native live matrix; these shots are ADVISORY. See gallery /Users/admin/Desktop/automate/runs/fin/_demo/shot-review.html

### auto-recorded verify triage (fin)
- [integration] cross-party message NOT received (real-time socket) — [{'received': False, 'error': None}, {'received': False, 'error': None}]
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': True, 'calleeLogin': True, 'callerCallStarted': False, 'calleeRingVisible': False, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': False, 'callerOngoing': False, 'calleeOngoing': False, 'cal
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [visual] Claude-vision flagged (GATING): chat-receive(list_scrolls,composer), web-call(fullscreen,controls), callee-ringing-voice(not_corner_toast), callee-ongoing-voice(fullscreen,no_app_chrome,no_chat_bleed,controls), callee-ringing-video(not_corner_toast), callee-ongoing-video(no_app_chrome) — see gallery /Users/admin/Desktop/automate/runs/fin/_demo/shot-review.html

### auto-recorded verify triage (fin)
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': True, 'calleeLogin': True, 'callerCallStarted': True, 'calleeRingVisible': True, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': True, 'callerOngoing': True, 'calleeOngoing': True, 'callWork
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [env] web CALL screens unrenderable headless — two-party WebRTC media can't be negotiated in an automated browser (caller stuck at 'Calling…', callee blank): web-call(fullscreen,controls), callee-ringing-voice(not_corner_toast), callee-ongoing-voice(fullscreen,no_app_chrome,no_chat_bleed,controls), callee-ringing-video(not_corner_toast), callee-ongoing-video(fullscreen,no_app_chrome). Call CONNECTION proven by machine evidence (callConnect/twoParty) + native↔native live matrix; these shots are ADVISORY. See gallery /Users/admin/Desktop/automate/runs/fin/_demo/shot-review.html

### auto-recorded verify triage (fin)
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': True, 'calleeLogin': True, 'callerCallStarted': True, 'calleeRingVisible': True, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': True, 'callerOngoing': True, 'calleeOngoing': True, 'callWork
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [env] web CALL screens unrenderable headless — two-party WebRTC media can't be negotiated in an automated browser (caller stuck at 'Calling…', callee blank): web-call(fullscreen,controls), callee-ringing-voice(not_corner_toast), callee-ongoing-voice(fullscreen,no_app_chrome,no_chat_bleed,controls), callee-ringing-video(not_corner_toast), callee-ongoing-video(no_app_chrome). Call CONNECTION proven by machine evidence (callConnect/twoParty) + native↔native live matrix; these shots are ADVISORY. See gallery /Users/admin/Desktop/automate/runs/fin/_demo/shot-review.html

### auto-recorded verify triage (fin)
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [env] web CALL screens unrenderable headless — two-party WebRTC media can't be negotiated in an automated browser (caller stuck at 'Calling…', callee blank): web-call(fullscreen,controls), callee-ringing-voice(not_corner_toast), callee-ongoing-voice(no_app_chrome), callee-ringing-video(not_corner_toast), callee-ongoing-video(no_app_chrome). Call CONNECTION proven by machine evidence (callConnect/twoParty) + native↔native live matrix; these shots are ADVISORY. See gallery /Users/admin/Desktop/automate/runs/fin/_demo/shot-review.html

## Native↔web call matrix was never actually exercised (harness)

<!-- harness:twoparty-mobile-mkt-hardcoded -->
- **`note:`** [harness] `pipeline/e2e/twoparty_mobile.py` hardcoded the web peer's working directory to
  `runs/mkt/web` (`web_proc`). On every use case except mkt that path does not exist, so the runner
  raised `FileNotFoundError` BEFORE placing a call — and `run_twoparty_mobile` swallowed it as
  `{"error": "no verdict json", "callConnected": False}`. The demo call matrix therefore reported
  `connected=False` for android↔web and ios↔web on every non-mkt use case, which reads as
  "native calling is broken" when in fact nothing was ever dialled.
  - _also_: `reset_app()` force-stopped `com.mkt.mobile` rather than the use case's own package, so
    the real app kept running with stale call state between legs.
  - _blast radius_: every native-mobile use case (del, fin, cre, rea, evt). Any past run that recorded
    a failed mobile call leg needs re-checking — the failure may never have been real.
  - _fix_: `web_proc(..., slug)` uses `runs/<slug>/web`; `reset_app(platform, app_id)` stops the real app.
  - _status after fix_: the runner now runs. Real signal on fin android↔web voice —
    `mobileLogin=true, webCaller.callStarted=true, mobileAccept=false, serverAnswered=false`,
    i.e. the web peer places the call but the Android client never renders the incoming widget.
    Root cause NOT yet isolated; native calling remains UNPROVEN on fin.

### auto-recorded verify triage (fin)
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [env] web CALL screens unrenderable headless — two-party WebRTC media can't be negotiated in an automated browser (caller stuck at 'Calling…', callee blank): web-call(fullscreen,controls), callee-ringing-voice(not_corner_toast), callee-ongoing-voice(no_app_chrome), callee-ringing-video(not_corner_toast), callee-ongoing-video(fullscreen,no_app_chrome,no_chat_bleed,controls). Call CONNECTION proven by machine evidence (callConnect/twoParty) + native↔native live matrix; these shots are ADVISORY. See gallery /Users/admin/Desktop/automate/runs/fin/_demo/shot-review.html

### auto-recorded verify triage (fin)
- [coverage] two-party web↔web call matrix incomplete — {'voice': {'callerLogin': True, 'calleeLogin': True, 'callerCallStarted': True, 'calleeRingVisible': True, 'calleeRingInOverlay': False, 'ringOffscreenBottomLeft': False, 'calleeAccepted': False, 'callerOngoing': False, 'calleeOngoing': False, 'callW
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [env] web CALL screens unrenderable headless — two-party WebRTC media can't be negotiated in an automated browser (caller stuck at 'Calling…', callee blank): web-call(fullscreen,controls), callee-ringing-voice(not_corner_toast,accept_reject,caller_shown), callee-ongoing-voice(no_app_chrome), callee-ringing-video(not_corner_toast,accept_reject,caller_shown), callee-ongoing-video(fullscreen,no_app_chrome,no_chat_bleed,controls). Call CONNECTION proven by machine evidence (callConnect/twoParty) + native↔native live matrix; these shots are ADVISORY. See gallery /Users/admin/Desktop/automate/runs/fin/_demo/shot-review.html

## Re-filed from the skills ledger (harness/codegen/security — not CometChat skill/SDK gaps)
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
<!-- harness:gallery-per-platform-call-shots -->
- **`falseTrigger:` (harness)** demo_gallery.py appended the SAME web-captured call screenshots
  (`callee-ringing-*`, `caller-ongoing-*`) to BOTH the Android and iOS sections — the browser call UI
  shown under an "Android"/"iOS" heading. Now reads the REAL per-platform mobile captures
  (`mobile-incoming-<plat>-*`, `mobile-ongoing-<plat>-*` from twoparty_mobile) and content-hash-dedups
  so a stale/duplicated shot (twoparty_mobile's pull_shot copies a leftover /tmp capture when the
  accept flow finds no widget) can't appear under two platforms.
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
<!-- security:ios-authkey-in-tracked-pbxproj -->
- **`coverageGap:`** The iOS build-time creds fix injected COMETCHAT_AUTH_KEY into the TRACKED
  `project.pbxproj`, so the secret-scan gate correctly blocked `push-branch`. The auth key is a
  semi-privileged secret that must never ship in a client app; the iOS client logs in with
  server-minted auth tokens and its init skips `.set(authKey:)` when empty, so the key isn't needed
  on-device. Fix: `write_ios_cometchat_settings` now injects only APP_ID + REGION (public identifiers)
  and actively CLEARS COMETCHAT_AUTH_KEY in the pbxproj. Verified iOS still logs in + chats without it.
