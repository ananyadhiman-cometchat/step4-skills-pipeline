
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

### UC2 demo — deeper findings (all fixed/recorded)
- **[containerize] JWT_SECRET too short → login 500 → app stuck on 'loading'.** compose set
  `JWT_SECRET: dev-jwt-secret-smoke-test` (25 chars/200 bits); tymon/jwt-auth Lcobucci needs ≥256 bits.
  FIXED (com: 64-char secret) + generalized in the containerize prompt (auth secrets ≥32 bytes).
- **[pipeline] iOS bundle id ≠ android applicationId (Flutter).** Flutter generated
  io.com.communityForum (iOS) vs io.com.community_forum (android). resolve_ios_bundle() reads the
  Xcode PRODUCT_BUNDLE_IDENTIFIER; provider now uses per-platform ids. (iOS was launching the wrong
  bundle → sim home screen.)
- **[skills] Flutter login testIDs use widget Key(), which Maestro can't see.** login-shot now logs in
  via the demo-account BUTTON (visible text). The build prompt should mandate Semantics(identifier:)
  for Flutter login fields (not just Key) so testID-based automation works.
- **[containerize/provider] Flutter web API_URL must reach the backend.** web built with API_URL=/api
  (relative) but nginx on :3000 doesn't proxy /api → login 404s. Fix: build web with the absolute host
  backend URL (http://localhost:8080/api) OR add an nginx /api→backend:8000 proxy in the web Dockerfile.
- **[automation] Maestro login-shot on Flutter timing** — demo-chip fill + immediate Sign In tap can
  race; android/ios login-shot needs a settle between the chip tap and submit. Backend login itself
  works (verified via API after the JWT fix).
- **[RESOLVED] web login** — nginx now proxies /api→backend:8000; login verified returning a token
  through the proxy AND direct. App + login are FUNCTIONAL on all platforms.
- **[skills/build] Flutter automation limits (logged-in screenshot).** Maestro sees Flutter TEXT on
  android/ios but reliably driving the demo-chip→submit login is finicky; Playwright can't drive
  Flutter WEB at all (CanvasKit = no DOM). To automate logged-in screenshots on Flutter, the build
  prompt should mandate (a) Semantics(identifier: 'email-input'/...) on inputs+buttons, and (b) the
  Flutter web HTML renderer (--web-renderer html) or the a11y tree. App works; only the automated
  post-login screenshot is blocked by these build-time choices.

### auto-recorded verify triage (com)
- [integration] cross-party message NOT received (real-time socket) — [{'received': False, 'error': None}, {'received': False, 'error': None}]
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [visual] Claude-vision flagged: web-call(fullscreen,no_app_chrome,no_chat_bleed,controls), chat-receive(list_scrolls,composer) — see gallery /Users/admin/Desktop/automate/runs/com/_demo/shot-review.html

### auto-recorded verify triage (com)
- [integration] cross-party message NOT received (real-time socket) — [{'received': False, 'built': True, 'error': None}, {'received': False, 'built': True, 'error': None}]
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [visual] Claude-vision flagged: web-call(fullscreen,no_app_chrome,no_chat_bleed,controls), chat-receive(list_scrolls,composer) — see gallery /Users/admin/Desktop/automate/runs/com/_demo/shot-review.html

### auto-recorded verify triage (com)
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
- [visual] Claude-vision flagged: web-call(fullscreen,no_app_chrome,no_chat_bleed,controls) — see gallery /Users/admin/Desktop/automate/runs/com/_demo/shot-review.html

### auto-recorded verify triage (com)
- [integration] cross-party message NOT received (real-time socket) — [{'received': False, 'built': True, 'error': None}, {'received': False, 'built': True, 'error': None}]
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)

### auto-recorded verify triage (com)
- [setup] AI moderation not observed — no moderation transform observed (extension likely not enabled in dashboard) (enable the moderation/data-masking extension in the CometChat dashboard)
