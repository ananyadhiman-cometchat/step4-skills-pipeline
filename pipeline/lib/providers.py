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
        gradle = app / "android/app/build.gradle"
        if gradle.exists():
            for line in gradle.read_text().splitlines():
                if "applicationId" in line:
                    return line.split('"')[1] if '"' in line else line.split("'")[1]
        return "com.example.app"

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
        # Android — apk with API_URL for the emulator→host route
        if mobile.boot_android():
            code, o = _sh(f'export JAVA_HOME="{mobile.JDK17}"; export ANDROID_HOME="{mobile.SDK}"; '
                          f'flutter build apk --release --dart-define=API_URL={ctx["api_android"]} {defs}', cwd=str(app))
            apk = next(iter((app / "build/app/outputs/flutter-apk").glob("app-release.apk")), None) if code == 0 else None
            p = str(demo / "android.png"); ok = False
            if apk:
                ok = mobile.install_launch_shot_android(str(apk), p, pkg=self._pkg(app))
            out["android"] = {"ok": ok, "path": p, "buildExit": code, "tail": mobile._tail(o)}
        # iOS — simulator .app (no codesign) → install via simctl
        mobile.boot_ios()
        code, o = _sh(f'{mobile.UTF8}; flutter build ios --simulator --debug '
                      f'--dart-define=API_URL={ctx["api_ios"]} {defs}', cwd=str(app))
        appbin = next(iter((app / "build/ios/iphonesimulator").glob("*.app")), None) if code == 0 else None
        p = str(demo / "ios.png"); ok = False
        if appbin:
            ok = mobile.install_launch_shot_ios(str(appbin), p, bundle=self._pkg(app))
        out["ios"] = {"ok": ok, "path": p, "buildExit": code, "tail": mobile._tail(o)}
        # Web — static build; the boot/containerize stage serves build/web on :3000
        code, o = _sh(f'flutter build web --dart-define=API_URL={ctx.get("api_web","/api")} {defs}', cwd=str(app))
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
