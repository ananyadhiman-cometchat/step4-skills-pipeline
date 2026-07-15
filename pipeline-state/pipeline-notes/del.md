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
