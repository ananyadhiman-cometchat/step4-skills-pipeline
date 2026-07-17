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
