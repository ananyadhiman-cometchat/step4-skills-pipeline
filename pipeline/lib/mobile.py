"""mobile — boot iOS simulator + Android emulator, build a STANDALONE release app,
install/launch, and screenshot. Used by the `demo` (manual-verify) stage.

Hard-won recipe (UC1 mobile hardening — all generalized here):
- `expo prebuild --clean` so native projects match app.json (avoids stale namespace).
- Android gradle needs JDK 17 (JDK 26 → "Unsupported class file major version 70") + ANDROID_HOME.
- iOS pods need LANG=UTF-8 (CocoaPods Ruby "ASCII-8BIT" encoding error otherwise).
- Screenshot from a RELEASE build (JS bundle embedded) — NOT a Metro dev build. Watchman's
  watch-project hangs and Metro's node-watcher hits EMFILE; a release build needs neither.
- Bake EXPO_PUBLIC_API_URL at build time: Android→10.0.2.2, iOS→localhost (host backend port 8080).
- Dismiss the Android 15 "16 KB compatibility" dialog before screenshotting.
"""
from __future__ import annotations
import os, re, subprocess, time
from pathlib import Path

SDK = os.path.expanduser(os.environ.get("ANDROID_HOME") or "~/Library/Android/sdk")


def _is_jdk17(home: str) -> bool:
    """True only if `home` is REALLY JDK 17 — `java_home -v 17` silently returns a NEWER JDK when 17
    isn't installed, and using e.g. JDK 26 is the 'Unsupported class file major version 70' bug."""
    java = os.path.join(home, "bin", "java")
    if not os.path.isfile(java):
        return False
    try:
        v = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=10)
        return 'version "17' in (v.stderr + v.stdout)
    except Exception:
        return False


def _jdk17_home() -> str:
    """Resolve a REAL JDK 17 (Homebrew openjdk@17 → brew --prefix → validated java_home) instead of a
    hardcoded Apple-Silicon path. Never returns a newer JDK: the classic-path fallback is left for the
    selfheal jdk17 rule to report honestly as 'not installed' rather than silently using JDK 26."""
    for p in ("/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home",
              "/usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"):
        if _is_jdk17(p):
            return p
    try:
        r = subprocess.run(["brew", "--prefix", "openjdk@17"], capture_output=True, text=True, timeout=15)
        cand = os.path.join(r.stdout.strip(), "libexec/openjdk.jdk/Contents/Home")
        if r.returncode == 0 and _is_jdk17(cand):
            return cand
    except Exception:
        pass
    try:
        r = subprocess.run(["/usr/libexec/java_home", "-v", "17"], capture_output=True, text=True, timeout=10)
        home = r.stdout.strip()
        if r.returncode == 0 and _is_jdk17(home):   # ONLY accept if it is genuinely 17
            return home
    except Exception:
        pass
    return "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"


JDK17 = _jdk17_home()
ADB = f"{SDK}/platform-tools/adb"
UTF8 = 'export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8'


def _run(cmd, cwd=None, timeout=2400, env=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, timeout=timeout, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env={**os.environ, **(env or {})})
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        return 124, f"TIMEOUT {timeout}s\n{(e.output or '')[-1500:]}"


def _sh(cmd, cwd=None, timeout=2400):
    return _run(["bash", "-lc", cmd], cwd=cwd, timeout=timeout)


def _tail(s, n=25):
    return "\n".join((s or "").splitlines()[-n:])


def cleanup_build_artifacts(mobile_dir: Path | None = None) -> None:
    """Reclaim the multi-GB transients each release build leaves — WITHOUT this a full sweep
    fills the disk and crashes Docker (learned the hard way on UC1: gradle caches hit 14GB,
    iOS DerivedData 6GB). Safe: everything here regenerates on the next build."""
    for p in Path("/tmp").glob("iosbuild*"):
        subprocess.run(["rm", "-rf", str(p)], capture_output=True)   # iOS DerivedData (biggest transient)
    subprocess.run(["docker", "builder", "prune", "-f"], capture_output=True)  # docker layer cache
    if mobile_dir:
        for d in [mobile_dir / "android/app/build", mobile_dir / "ios/build"]:
            subprocess.run(["rm", "-rf", str(d)], capture_output=True)


def disk_free_gb() -> int:
    r = subprocess.run(["df", "-g", "/"], capture_output=True, text=True)
    try:
        return int(r.stdout.splitlines()[-1].split()[3])
    except Exception:
        return 999


def prebuild_clean(mobile_dir: Path) -> tuple[int, str]:
    """Regenerate native projects from app.json so namespace/config are consistent."""
    return _sh(f'{UTF8}; npx expo prebuild --clean', cwd=str(mobile_dir))


def write_cometchat_env(mobile_dir: Path, cfg: dict) -> bool:
    """Bake the REAL provisioned CometChat creds into mobile/.env so Expo inlines them into the JS
    bundle at build time. Without this the app falls back to the .env.example placeholder
    ('your_app_id_here') and the SDK dials your_app_id_here.apiclient-*.cometchat.io — a dead host,
    so the real-time socket never connects: chat presence works (REST login) but the conversation
    list spins forever and INCOMING CALLS NEVER ARRIVE. Hard-won on UC1 iOS. Re-apply before every
    mobile build (a prior `expo prebuild`/scaffold may have copied the placeholder .env back)."""
    app_id = cfg.get("COMETCHAT_APP_ID"); region = cfg.get("COMETCHAT_REGION", "us")
    auth_key = cfg.get("COMETCHAT_AUTH_KEY", "")
    if not app_id:
        return False
    (mobile_dir / ".env").write_text(
        "# CometChat — injected from the pipeline env (real provisioned app)\n"
        f"EXPO_PUBLIC_COMETCHAT_APP_ID={app_id}\n"
        f"EXPO_PUBLIC_COMETCHAT_REGION={region}\n"
        f"EXPO_PUBLIC_COMETCHAT_AUTH_KEY={auth_key}\n")
    return True


def enable_cleartext(mobile_dir: Path) -> None:
    """RELEASE builds block cleartext HTTP by default (Android usesCleartextTraffic, iOS ATS).
    The local backend is HTTP, so the app's requests are killed before leaving the device
    ("login failed" with NO request reaching the backend). Re-apply after every prebuild --clean."""
    manifest = mobile_dir / "android/app/src/main/AndroidManifest.xml"
    if manifest.exists():
        t = manifest.read_text()
        if "usesCleartextTraffic" not in t:
            manifest.write_text(t.replace("<application ", '<application android:usesCleartextTraffic="true" ', 1))
    for plist in mobile_dir.glob("ios/*/Info.plist"):
        pb = "/usr/libexec/PlistBuddy"
        subprocess.run([pb, "-c", "Add :NSAppTransportSecurity dict", str(plist)], capture_output=True)
        subprocess.run([pb, "-c", "Add :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true", str(plist)], capture_output=True)
        subprocess.run([pb, "-c", "Set :NSAppTransportSecurity:NSAllowsArbitraryLoads true", str(plist)], capture_output=True)


# ---------- Android (standalone release APK) ----------
def boot_android(avd="Pixel_10") -> bool:
    if "emulator-" in subprocess.run([ADB, "devices"], text=True, capture_output=True).stdout:
        return True
    subprocess.Popen([f"{SDK}/emulator/emulator", "-avd", avd, "-no-snapshot",
                      "-no-boot-anim", "-no-audio", "-gpu", "swiftshader_indirect"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([ADB, "wait-for-device"], timeout=240)
    for _ in range(80):
        if subprocess.run([ADB, "shell", "getprop", "sys.boot_completed"],
                          text=True, capture_output=True).stdout.strip() == "1":
            return True
        time.sleep(3)
    return False


def build_android(mobile_dir: Path, api_url: str) -> dict:
    andro = mobile_dir / "android"
    (andro / "local.properties").write_text(f"sdk.dir={SDK}\n")
    # RN/Expo prebuild references @color/splashscreen_background but often omits it from colors.xml →
    # assembleRelease resource-linking fails. Proactively define it (idempotent, records the codegen gap).
    try:
        from lib import selfheal
        fixes = selfheal.ensure_expo_android_splash(mobile_dir)
        if fixes:
            print(f"  self-heal (android splash): {[f['rule'] for f in fixes]}")
    except Exception as e:
        print(f"  self-heal (android splash) skipped: {e}")
    # `clean` is REQUIRED: EXPO_PUBLIC_API_URL is inlined into the JS bundle at bundle time, but a plain
    # assembleRelease reuses the cached bundle task (env vars don't invalidate it) → stale API URL.
    cmd = (f'export JAVA_HOME="{JDK17}"; export ANDROID_HOME="{SDK}"; export ANDROID_SDK_ROOT="{SDK}"; '
           f'export EXPO_PUBLIC_API_URL="{api_url}"; ./gradlew clean assembleRelease')
    code, out = _sh(cmd, cwd=str(andro))
    apk = next(iter((andro / "app/build/outputs/apk/release").glob("*.apk")), None) if code == 0 else None
    return {"platform": "android", "exitCode": code, "apk": str(apk) if apk else None, "tail": _tail(out)}


def _adb(*a, timeout=60):
    return subprocess.run([ADB, *a], text=True, capture_output=True, timeout=timeout)


def _fg_pkg_android() -> str:
    """The package currently in the foreground (resumed) — to verify the RIGHT app is showing."""
    out = _adb("shell", "dumpsys", "activity", "activities").stdout
    for key in ("mResumedActivity", "topResumedActivity", "mCurrentFocus"):
        for line in out.splitlines():
            if key in line and "/" in line:
                for tok in line.split():
                    if "/" in tok and "." in tok:
                        return tok.split("/")[0].strip("{").strip()
    return ""


def clean_stale_apps(keep_pkg: str | None = None) -> list[str]:
    """Uninstall PREVIOUS use cases' apps from the emulator so a demo screenshot can never capture a
    stale app (UC1 hardcoded teardown to com.mkt.mobile and left every prior app behind — that's why
    UC2's Android shot showed the Marketplace app). Removes step4-shaped third-party packages except
    `keep_pkg`. Idempotent."""
    removed = []
    out = _adb("shell", "pm", "list", "packages", "-3").stdout   # -3 = third-party only (safe)
    pats = ("com.mkt", "io.com", "com.example", "com.step4", ".mobile", "forum", "marketplace",
            "deskline", "delivery", "dating", "fintech", "creator", "rideshare", "event")
    for line in out.splitlines():
        p = line.replace("package:", "").strip()
        if p and p != keep_pkg and any(x in p for x in pats):
            _adb("uninstall", p); removed.append(p)
    return removed


def _apk_package(apk: str) -> str | None:
    """Read the real applicationId straight from the built APK (aapt), so the launch check never uses a
    stale hardcoded default (that installed com.del.delivery but tried to launch com.mkt.mobile)."""
    try:
        aapt = next(iter(Path(SDK).glob("build-tools/*/aapt")), None)
        if not aapt:
            return None
        out = subprocess.run([str(aapt), "dump", "badging", apk], capture_output=True, text=True).stdout
        m = re.search(r"package: name='([^']+)'", out)
        return m.group(1) if m else None
    except Exception:
        return None


def _app_bundle_id(app: str) -> str | None:
    """Read CFBundleIdentifier from the built .app's Info.plist (the real bundle id to launch)."""
    try:
        r = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleIdentifier",
                            f"{app}/Info.plist"], capture_output=True, text=True)
        b = r.stdout.strip()
        return b or None
    except Exception:
        return None


def install_launch_shot_android(apk: str, out_png: str, pkg=None) -> bool:
    pkg = pkg or _apk_package(apk) or "com.mkt.mobile"   # derive the REAL package from the apk
    clean_stale_apps(keep_pkg=pkg)          # remove prior-UC apps so we can't screenshot the wrong one
    _adb("uninstall", pkg)                  # clean install of THIS app (no stale state)
    _adb("install", "-r", "-g", apk, timeout=180)   # -g pre-grants runtime perms (no dialog stealing foreground)
    _adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(6)
    sz = _adb("shell", "wm", "size").stdout   # dismiss the Android 15 "16 KB compatibility" dialog
    if "x" in sz:
        w, h = [int(x) for x in sz.split(":")[-1].strip().split("x")[:2]]
        _adb("shell", "input", "tap", str(int(w * 0.90)), str(int(h * 0.936)))
    # Poll until OUR app is foreground AND rendered real content. If it launched then vanished
    # (release-build crash — e.g. the go_router assertion), the foreground is NOT our pkg → FAIL,
    # so we never pass a screenshot of the launcher or a previous app.
    ok = False
    for _ in range(12):
        with open(out_png, "wb") as f:
            subprocess.run([ADB, "exec-out", "screencap", "-p"], stdout=f)
        fg = _fg_pkg_android()
        if fg == pkg and os.path.getsize(out_png) > 60000:
            ok = True; break
        time.sleep(6)
    if not ok:
        print(f"    android launch check: foreground='{_fg_pkg_android()}' expected='{pkg}' — app not showing (crash?)")
    return ok


# ---------- iOS (standalone release .app) ----------
def boot_ios(device="iPhone 16") -> bool:
    subprocess.run(["xcrun", "simctl", "boot", device], capture_output=True)
    subprocess.run(["open", "-a", "Simulator"], capture_output=True)
    subprocess.run(["xcrun", "simctl", "bootstatus", device], capture_output=True, timeout=180)
    return True


def build_ios(mobile_dir: Path, api_url: str) -> dict:
    ios = mobile_dir / "ios"
    ws = next(iter(ios.glob("*.xcworkspace")), None)
    scheme = ws.stem if ws else "Marketplace"
    # `clean build` so the embedded JS bundle regenerates with the current EXPO_PUBLIC_API_URL.
    # `-destination generic/platform=iOS Simulator` is REQUIRED on newer Xcode (16/26): with only
    # `-sdk iphonesimulator` and no destination, xcodebuild aborts "Found no destinations for the scheme
    # '<x>' and action clean" before it builds. The generic simulator destination needs no booted sim.
    cmd = (f'{UTF8}; pod install; export EXPO_PUBLIC_API_URL="{api_url}"; '
           f'xcodebuild -workspace {scheme}.xcworkspace -scheme {scheme} -configuration Release '
           f"-sdk iphonesimulator -destination 'generic/platform=iOS Simulator' "
           f'-derivedDataPath /tmp/iosbuild-{mobile_dir.parent.name} -quiet clean build')
    code, out = _sh(cmd, cwd=str(ios))
    app = next(Path(f"/tmp/iosbuild-{mobile_dir.parent.name}/Build/Products").glob("Release-*/*.app"), None) \
        if code == 0 else None
    return {"platform": "ios", "exitCode": code, "app": str(app) if app else None, "tail": _tail(out)}


def install_launch_shot_ios(app: str, out_png: str, bundle=None, device="iPhone 16") -> bool:
    bundle = bundle or _app_bundle_id(app) or "com.mkt.mobile"   # derive the REAL bundle from the .app
    subprocess.run(["xcrun", "simctl", "terminate", device, bundle], capture_output=True)
    subprocess.run(["xcrun", "simctl", "uninstall", device, bundle], capture_output=True)  # clean install
    subprocess.run(["xcrun", "simctl", "install", device, app], capture_output=True)
    r = subprocess.run(["xcrun", "simctl", "launch", device, bundle], capture_output=True, text=True)
    time.sleep(14)
    subprocess.run(["xcrun", "simctl", "io", device, "screenshot", out_png], capture_output=True)
    # A launched-then-crashed app (or a debug assertion red screen) still produces a screenshot — the
    # vision judge (app_alive rubric) in the demo stage flags "red error box / blank / spinner".
    return os.path.getsize(out_png) > 40000 if os.path.exists(out_png) else False


# ---------- teardown ----------
def teardown_mobile(ios_bundle=None, android_pkg=None, device="iPhone 16"):
    if ios_bundle:
        subprocess.run(["xcrun", "simctl", "uninstall", device, ios_bundle], capture_output=True)
    subprocess.run(["xcrun", "simctl", "shutdown", device], capture_output=True)
    subprocess.run(["osascript", "-e", 'quit app "Simulator"'], capture_output=True)
    if android_pkg:
        _adb("uninstall", android_pkg)
    _adb("emu", "kill")
    return {"ios": True, "android": True}
