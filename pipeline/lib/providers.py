"""providers — per-stack DEMO recipes (build → install/launch → screenshot), one provider per
platform-stack family, so the demo stage is stack-GENERAL instead of RN-only.

Dispatch by component (kind, stack):
    kind 'mobile'  (React Native)      -> RNProvider        [android, ios]
    kind 'app'     (Flutter v5/v6)     -> FlutterProvider   [android, ios, web]
    kind 'android' (Compose/Kotlin)    -> AndroidNativeProvider [android]
    kind 'ios'     (Swift)             -> IOSNativeProvider  [ios]
    kind 'web'     (Next/React/…/Flutter) handled by the docker/served path in stage_demo.

Every provider runs `selfheal.preapply` before building (cleartext + real CometChat creds, made
stack-aware in selfheal.py) so the UC1 bugs never recur on any stack. Providers reuse mobile.py's
device helpers (boot_android/boot_ios, ADB, SDK, JDK17) and screenshot pollers.

Native (Compose/Kotlin/Swift) recipes are written against the standard toolchains; they harden on
the first native use case (UC3/5/6/8/10) the same way RN hardened on UC1 and Flutter on UC2.
"""
from __future__ import annotations
import os, subprocess, time
from pathlib import Path
from lib import mobile, selfheal


def _sh(cmd, cwd=None, timeout=2400, env=None):
    return mobile._sh(cmd, cwd=cwd, timeout=timeout) if env is None else mobile._run(
        ["bash", "-lc", cmd], cwd=cwd, timeout=timeout, env=env)


def _guards(ctx: dict):
    g = selfheal.preapply({"stage": "demo", "kind": ctx["kind"], "stack": ctx["stack"],
                           "repo_dir": ctx["repo_dir"], "comp_dir": ctx["app_dir"],
                           "mobile_dir": ctx["app_dir"], "env_file": ctx.get("env_file", ""),
                           "integrated": ctx.get("integrated")})
    if g:
        print(f"  self-heal guards ({ctx['stack']}): {[x['rule'] for x in g]}")
    return g


def write_flutter_env(app: Path, api_url: str, env_file: str = "") -> None:
    """Write the app's runtime `.env` asset (flutter_dotenv) with API_URL (+ real CometChat creds) and
    guarantee it's a declared asset. Flutter apps split into two config conventions and we cover both:
    apps that read `dotenv.env['API_URL']` need this bundled `.env`; apps that read `--dart-define` get
    the value from the build flag. Passing only one leaves the other convention on its build-time default
    (→ the app dials the wrong host and every call fails as a generic 'Connection error').
    API_URL is the scheme://host:port BASE with NO path — the app appends the full route (…/api/…),
    so a base that already ends in /api produces a fatal double `/api/api/...` 404."""
    app = Path(app)
    lines = {"API_URL": api_url.rstrip("/"), "ENABLE_DEMO_LOGINS": "true"}
    if env_file and os.path.exists(os.path.expanduser(env_file)):
        try:
            from lib import cometchat
            cfg = cometchat._cfg(env_file)
            for k in ("COMETCHAT_APP_ID", "COMETCHAT_REGION", "COMETCHAT_AUTH_KEY"):
                if cfg.get(k):
                    lines[k] = cfg[k]
        except Exception:
            pass
    (app / ".env").write_text("".join(f"{k}={v}\n" for k, v in lines.items()))
    # ensure `.env` is a bundled asset (flutter_dotenv loads it via rootBundle at runtime)
    pub = app / "pubspec.yaml"
    if pub.exists():
        t = pub.read_text()
        if "- .env" not in t:
            import re as _re
            nt = _re.sub(r"(\n\s*assets:\s*\n)", r"\1    - .env\n", t, count=1)
            if nt == t and "\nflutter:" in t:                       # no assets: block yet → add one
                nt = t.replace("\nflutter:", "\nflutter:\n  assets:\n    - .env", 1)
            if nt != t:
                pub.write_text(nt)


# ---------------- React Native (UC1/4/9) — delegates to the proven mobile.py ----------------
class RNProvider:
    family = "rn"; platforms = ["android", "ios"]

    def demo(self, ctx) -> dict:
        app = ctx["app_dir"]; demo = ctx["demo_dir"]
        mobile.prebuild_clean(app); _guards(ctx)
        out = {}
        if mobile.boot_android():
            b = mobile.build_android(app, ctx["api_android"]); p = str(demo / "android.png")
            ok = mobile.install_launch_shot_android(b["apk"], p) if b.get("apk") else False
            out["android"] = {"ok": ok, "path": p, "buildExit": b["exitCode"], "tail": b["tail"]}
        mobile.boot_ios()
        b = mobile.build_ios(app, ctx["api_ios"]); p = str(demo / "ios.png")
        ok = mobile.install_launch_shot_ios(b["app"], p) if b.get("app") else False
        out["ios"] = {"ok": ok, "path": p, "buildExit": b["exitCode"], "tail": b["tail"]}
        mobile.cleanup_build_artifacts(app)
        return out


# ---------------- Flutter (UC2/7) — one codebase → android + ios + web ----------------
class FlutterProvider:
    family = "flutter"; platforms = ["android", "ios", "web"]

    def _pkg(self, app: Path) -> str:
        # Use the shared resolver (reads build.gradle AND build.gradle.kts + app.json) — a bare
        # build.gradle reader misses Kotlin-DSL projects and falls back to the wrong com.example.app.
        return resolve_app_id("app", app) or "com.example.app"

    def demo(self, ctx) -> dict:
        app = ctx["app_dir"]; demo = ctx["demo_dir"]; out = {}
        # Ensure ALL platform folders exist — codegen often scaffolds lib/ but not web/ios/android
        # ("This project is not configured for the web"). `flutter create .` is idempotent and
        # preserves lib/; it only adds the missing platform scaffolding.
        _sh("flutter create . --platforms=android,ios,web", cwd=str(app), timeout=300)
        _guards(ctx)  # writes .dart_define.json (creds) + cleartext (manifest/ATS) — AFTER create so it patches the real manifests
        _sh("flutter pub get", cwd=str(app), timeout=600)
        dd = app / ".dart_define.json"
        defs = f"--dart-define-from-file={dd}" if dd.exists() else ""
        # Android — apk with API_URL for the emulator→host route. Write BOTH the .env asset (dotenv apps)
        # and pass --dart-define (dart-define apps); either convention now points at the real backend.
        if mobile.boot_android():
            write_flutter_env(app, ctx["api_android"], ctx.get("env_file", ""))
            code, o = _sh(f'export JAVA_HOME="{mobile.JDK17}"; export ANDROID_HOME="{mobile.SDK}"; '
                          f'flutter build apk --release --dart-define=API_URL={ctx["api_android"]} {defs}', cwd=str(app))
            apk = next(iter((app / "build/app/outputs/flutter-apk").glob("app-release.apk")), None) if code == 0 else None
            p = str(demo / "android.png"); ok = False
            and_id = resolve_app_id("app", app) or "com.example.app"
            if apk:
                ok = mobile.install_launch_shot_android(str(apk), p, pkg=and_id)
            out["android"] = {"ok": ok, "path": p, "buildExit": code, "appId": and_id, "tail": mobile._tail(o)}
        # iOS — simulator .app (no codesign) → install via simctl. iOS bundle id ≠ android applicationId.
        mobile.boot_ios()
        write_flutter_env(app, ctx["api_ios"], ctx.get("env_file", ""))
        code, o = _sh(f'{mobile.UTF8}; flutter build ios --simulator --debug '
                      f'--dart-define=API_URL={ctx["api_ios"]} {defs}', cwd=str(app))
        appbin = next(iter((app / "build/ios/iphonesimulator").glob("*.app")), None) if code == 0 else None
        p = str(demo / "ios.png"); ok = False
        ios_bundle = resolve_ios_bundle(app) or self._pkg(app)
        if appbin:
            ok = mobile.install_launch_shot_ios(str(appbin), p, bundle=ios_bundle)
        out["ios"] = {"ok": ok, "path": p, "buildExit": code, "appId": ios_bundle, "tail": mobile._tail(o)}
        # Web — static build; the boot/containerize stage serves build/web on :3000. API_URL is EMPTY so
        # the app's relative fetch (`${API_URL}/api/...` → `/api/...`) is proxied by nginx to the backend.
        web_api = ctx.get("api_web", "")
        write_flutter_env(app, web_api, ctx.get("env_file", ""))
        code, o = _sh(f'flutter build web --dart-define=API_URL={web_api} {defs}', cwd=str(app))
        out["web"] = {"ok": code == 0, "buildExit": code, "built": str(app / "build/web"), "tail": mobile._tail(o)}
        mobile.cleanup_build_artifacts(app)
        return out


# ---------------- Native Android — Compose v6 / Kotlin v5 (UC3/5/6/8/10) ----------------
class AndroidNativeProvider:
    family = "android-native"; platforms = ["android"]

    def demo(self, ctx) -> dict:
        app = ctx["app_dir"]; demo = ctx["demo_dir"]; _guards(ctx)
        (app / "local.properties").write_text(f"sdk.dir={mobile.SDK}\n")
        out = {}
        if mobile.boot_android():
            code, o = _sh(f'export JAVA_HOME="{mobile.JDK17}"; export ANDROID_HOME="{mobile.SDK}"; '
                          f'./gradlew assembleDebug', cwd=str(app))
            apk = next(iter((app / "app/build/outputs/apk/debug").glob("*.apk")), None) if code == 0 else None
            p = str(demo / "android.png"); ok = mobile.install_launch_shot_android(str(apk), p) if apk else False
            out["android"] = {"ok": ok, "path": p, "buildExit": code, "tail": mobile._tail(o)}
        return out


# ---------------- Native iOS — Swift (UC3/5/6/8/10) ----------------
class IOSNativeProvider:
    family = "ios-native"; platforms = ["ios"]

    def demo(self, ctx) -> dict:
        app = ctx["app_dir"]; demo = ctx["demo_dir"]; _guards(ctx)
        ws = next(iter(app.glob("*.xcworkspace")), None) or next(iter(app.glob("*.xcodeproj")), None)
        flag = "-workspace" if ws and ws.suffix == ".xcworkspace" else "-project"
        scheme = ws.stem if ws else app.name
        mobile.boot_ios()
        dd = f"/tmp/iosnative-{app.parent.name}"
        code, o = _sh(f'{mobile.UTF8}; [ -f Podfile ] && pod install || true; '
                      f'xcodebuild {flag} {ws.name if ws else scheme} -scheme {scheme} -configuration Debug '
                      f'-sdk iphonesimulator -derivedDataPath {dd} -quiet build', cwd=str(app))
        appbin = next(Path(f"{dd}/Build/Products").glob("Debug-iphonesimulator/*.app"), None) if code == 0 else None
        p = str(demo / "ios.png"); ok = mobile.install_launch_shot_ios(str(appbin), p) if appbin else False
        subprocess.run(["rm", "-rf", dd], capture_output=True)
        return {"ios": {"ok": ok, "path": p, "buildExit": code, "tail": mobile._tail(o)}}


_REGISTRY = {"rn": RNProvider, "flutter": FlutterProvider,
             "android-native": AndroidNativeProvider, "ios-native": IOSNativeProvider}


def ensure_flutter_web_semantics(app_dir) -> bool:
    """Guarantee the app forces Flutter's accessibility tree on at startup. Flutter web is CanvasKit-only
    (no DOM); the flt-semantics tree — the only thing web automation can drive — is NOT built unless the
    app calls SemanticsBinding.instance.ensureSemantics() (or the user clicks the a11y placeholder). The
    baseline may have it, but the CometChat integrate codegen rewrites main.dart from scratch and drops
    it, so the web chat-receive proof then finds no inputs. Inject it deterministically before every web
    build. Idempotent. Returns True if present/added."""
    main = Path(app_dir) / "lib" / "main.dart"
    if not main.exists():
        return False
    t = main.read_text()
    if "ensureSemantics" in t:
        return True
    import re as _re
    if "package:flutter/semantics.dart" not in t:
        t = t.replace("import 'package:flutter/material.dart';",
                      "import 'package:flutter/material.dart';\nimport 'package:flutter/semantics.dart';", 1)
    call = "  SemanticsBinding.instance.ensureSemantics();  // web a11y tree for automation\n"
    nt = _re.sub(r"(WidgetsFlutterBinding\.ensureInitialized\(\);\n)", r"\1" + call, t, count=1)
    if nt == t:   # no ensureInitialized() → add both at the top of main()
        nt = _re.sub(r"(main\(\)\s*async\s*\{\n)",
                     r"\1  WidgetsFlutterBinding.ensureInitialized();\n" + call, t, count=1)
    if nt == t:
        return False
    main.write_text(nt)
    return True


def host_build_flutter_web(app_dir, api_url: str = "", env_file: str = "") -> dict:
    """Build Flutter web on the HOST (the validated Flutter version) so the web Dockerfile can serve
    the static `build/web` via nginx — no Flutter-version drift between validation and the container.
    Call before compose_up for any Flutter use case. Idempotent (ensures the web platform first).
    API_URL defaults to EMPTY so the served app's fetches are relative (`/api/...`) and nginx proxies
    them to the backend — an absolute http://localhost:8080 would break in the browser (CORS / wrong
    origin). Writes the .env asset too (this app reads flutter_dotenv, not --dart-define)."""
    app_dir = Path(app_dir)
    if not (app_dir / "pubspec.yaml").exists():
        return {"ok": False, "note": "not a flutter app"}
    _sh("flutter create . --platforms=web", cwd=str(app_dir), timeout=300)
    write_flutter_env(app_dir, api_url, env_file)
    ensure_flutter_web_semantics(app_dir)   # the flt-semantics tree the web e2e drives (survives integrate rewrite)
    code, out = _sh(f"flutter build web --release --dart-define=API_URL={api_url}", cwd=str(app_dir), timeout=900)
    return {"ok": code == 0 and (app_dir / "build/web/index.html").exists(),
            "exitCode": code, "tail": mobile._tail(out)}


def build_install_flutter_android(app_dir, api_url: str, env_file: str = "", integrated: bool = True) -> dict:
    """Build the Flutter android release apk (with the CometChat creds + cleartext/INTERNET guards baked)
    and install it on the booted emulator. Shared by demo and by verify's mobile chat-receive proof.
    Returns {ok, appId, apk}. Runs the self-heal preapply guards first so a fresh integrate tree gets
    INTERNET + cleartext + the real creds every time."""
    app = Path(app_dir)
    if not mobile.boot_android():
        return {"ok": False, "note": "no android emulator"}
    selfheal.preapply({"stage": "verify", "kind": "app", "stack": "Flutter", "repo_dir": app.parent,
                       "comp_dir": app, "mobile_dir": app, "env_file": env_file, "integrated": integrated})
    _sh("flutter create . --platforms=android", cwd=str(app), timeout=300)
    _sh("flutter pub get", cwd=str(app), timeout=600)
    write_flutter_env(app, api_url, env_file)   # API_URL base + COMETCHAT_* creds into the .env asset
    dd = app / ".dart_define.json"
    defs = f"--dart-define-from-file={dd}" if dd.exists() else ""
    code, o = _sh(f'export JAVA_HOME="{mobile.JDK17}"; export ANDROID_HOME="{mobile.SDK}"; '
                  f'flutter build apk --release --dart-define=API_URL={api_url} {defs}', cwd=str(app), timeout=1800)
    apk = next(iter((app / "build/app/outputs/flutter-apk").glob("app-release.apk")), None) if code == 0 else None
    if not apk:
        return {"ok": False, "buildExit": code, "tail": mobile._tail(o)}
    aid = resolve_app_id("app", app) or "com.example.app"
    ADB = mobile.ADB
    subprocess.run([ADB, "install", "-r", "-g", str(apk)], capture_output=True, timeout=300)
    return {"ok": True, "appId": aid, "apk": str(apk), "buildExit": 0}


def login_and_shot(platform: str, app_id: str, email: str, password: str, out_png: str,
                   submit: str = "Sign In", role: str = "Member") -> dict:
    """Drive the mandated login (email-input/password-input/login-submit) as a real account and
    screenshot the LOGGED-IN home — proves the app reaches the backend (connectivity), which the
    launch screenshot alone does not. Uses Maestro on the booted device. Returns {ok, shot}."""
    maestro = os.path.expanduser("~/.maestro/bin/maestro")
    flow = Path(__file__).resolve().parent.parent / "e2e" / "mobile_flows" / "login_shot.flow.yaml"
    dev = []
    if platform == "ios":
        out = subprocess.run(["xcrun", "simctl", "list", "devices", "booted"], text=True, capture_output=True).stdout
        for line in out.splitlines():
            if "Booted" in line and "(" in line:
                dev = ["--device", line.split("(")[1].split(")")[0]]; break
    else:
        dev = ["--device", "emulator-5554"]
    cmd = [maestro, *dev, "test", str(flow), "-e", f"APP_ID={app_id}", "-e", f"EMAIL={email}",
           "-e", f"PASSWORD={password}", "-e", f"SUBMIT={submit}", "-e", f"ROLE={role}"]
    src = Path("/tmp/mobile-loggedin.png"); src.unlink(missing_ok=True)
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=180,
                           env={**os.environ, "PATH": os.path.expanduser("~/.maestro/bin:") + os.environ.get("PATH", "")})
        rc, tail = p.returncode, (p.stdout or "")[-200:]
    except subprocess.TimeoutExpired:
        rc, tail = 124, "login flow timed out (app may not have reached the login form)"
    if src.exists():
        Path(out_png).write_bytes(src.read_bytes()); src.unlink()
        return {"ok": rc == 0, "shot": out_png}
    return {"ok": False, "shot": None, "tail": tail}


def resolve_ios_bundle(app_dir) -> str | None:
    """iOS bundle id from the Xcode project — Flutter often generates a DIFFERENT id for iOS
    (camelCase, e.g. io.com.communityForum) than the Android applicationId (snake_case). Using the
    Android id to `simctl launch` silently fails → the sim shows the home screen."""
    import re
    pbx = Path(app_dir) / "ios/Runner.xcodeproj/project.pbxproj"
    if pbx.exists():
        for b in re.findall(r"PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);", pbx.read_text()):
            b = b.strip().strip('"')
            if b and "Test" not in b:
                return b
    for plist in Path(app_dir).glob("ios/Runner/Info.plist"):
        m = re.search(r"CFBundleIdentifier</key>\s*<string>([^<]+)", plist.read_text())
        if m and "$(" not in m.group(1):
            return m.group(1)
    return None


def resolve_app_id(kind: str, app_dir) -> str | None:
    """Read the mobile app's package/bundle id from the built app (for Maestro's appId), per stack."""
    app_dir = Path(app_dir)
    for g in (app_dir / "android/app/build.gradle", app_dir / "android/app/build.gradle.kts",
              app_dir / "app/build.gradle", app_dir / "build.gradle"):
        if g.exists():
            for line in g.read_text().splitlines():
                if "applicationId" in line and ('"' in line or "'" in line):
                    q = '"' if '"' in line else "'"
                    return line.split(q)[1]
    aj = app_dir / "app.json"                          # RN / Expo
    if aj.exists():
        import json
        d = json.loads(aj.read_text()).get("expo", {})
        return (d.get("android", {}).get("package") or d.get("ios", {}).get("bundleIdentifier"))
    return None


def mobile_provider(kind: str, stack: str):
    """Return the provider instance for a non-web client component, or None if it's not a client
    the demo stage builds on a device (web/backend are handled separately)."""
    fam = selfheal.stack_family(stack)
    # kind gives the coarse routing; stack_family disambiguates rn vs flutter vs native.
    if kind == "mobile":  fam = "rn"
    if kind == "app":     fam = "flutter"
    if kind == "android": fam = "android-native"
    if kind == "ios":     fam = "ios-native"
    cls = _REGISTRY.get(fam)
    return cls() if cls else None
