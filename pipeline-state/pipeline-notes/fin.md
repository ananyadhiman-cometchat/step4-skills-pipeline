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
