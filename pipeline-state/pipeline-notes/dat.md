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
  FIX applied: add `-destination 'generic/platform=iOS Simulator'` (needs no booted sim). Not yet
  end-to-end verified (a full RN iOS clean build is slow); will exercise on the next RN UC / demo re-run.
