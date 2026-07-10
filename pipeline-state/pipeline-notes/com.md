
### UC2 demo findings (Flutter baseline)
- **[codegen] Flutter app crashes on launch — go_router misconfig.** iOS (debug) red-screens with
  `route.parentNavigatorKey == null || route.parentNavigatorKey == navigatorKey` (go_router route.dart:481);
  Android (release) silently exits. Web renders (assert is debug-only). The flutter-v6 baseline codegen
  produced a sub-route whose `parentNavigatorKey` doesn't match its parent's navigator key. Needs the
  route tree fixed (or a self-heal). BASELINE bug (pre-CometChat).
- **[pipeline] stale apps never uninstalled → wrong-app screenshots.** The emulator held com.mkt.mobile
  (UC1) + com.example.deskline (older) + io.com.community_forum (UC2). teardown_mobile was hardcoded to
  com.mkt.mobile so prior apps persisted; the Android demo shot captured the leftover Marketplace app
  when the com app crash-exited. FIXED: mobile.clean_stale_apps() sweeps prior-UC apps; install does a
  clean (uninstall-first) install; android install now VERIFIES the foreground pkg == target (crash →
  ok=False, not a wrong-app pass); teardown resolves the real package.
- **[pipeline] screenshot reliability + connectivity check.** demo now (a) VISION-verifies every shot
  (app_alive rubric → catches red-error/blank/spinner/wrong-app — e.g. web stuck-loading), and (b) does
  a LOGIN→home screenshot per mobile client (providers.login_and_shot + login_shot.flow.yaml) to prove
  backend connectivity, vision-reviewed with the feed_loaded rubric. All general (every UC).
