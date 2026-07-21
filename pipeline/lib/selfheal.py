"""selfheal — autonomous repair of the KNOWN failure modes documented in UC1.

The UC1 run recorded a set of issues (gaps/mkt.md + pipeline-notes/mkt.md). Many are the same class
of build/boot failure that will recur on later use cases. Instead of a human re-diagnosing them each
time, this module encodes each as a RULE and lets the build/demo/verify stages auto-repair + retry
with NO human input.

Two entry points:
  - `preapply(ctx)`  — proactive guards run BEFORE a build (inject real creds, enable cleartext, …)
                       so the known bug never happens.
  - `heal(ctx, err)` — reactive: match a failure's output against rule signatures, apply the fix,
                       tell the caller to retry.

`ctx` (dict): {stage, kind, stack, repo_dir, comp_dir, mobile_dir?, env_file?, settings?, integrated?}.
Fixes are stack-aware via `stack_family()`; where a stack has no recipe yet the rule logs that
honestly rather than pretending to heal.
"""
from __future__ import annotations
import os, re, subprocess
from pathlib import Path


def stack_family(stack: str) -> str:
    s = (stack or "").lower()
    if "react native" in s or "expo" in s or s in ("rn",): return "rn"
    if "flutter" in s:                                      return "flutter"
    if "compose" in s or "kotlin" in s or "android" in s:  return "android-native"
    if "swift" in s or s.startswith("ios"):                return "ios-native"
    if "next" in s:      return "web-next"
    if "angular" in s:   return "web-angular"
    if "vue" in s:       return "web-vue"
    if "astro" in s:     return "web-astro"
    if "react" in s:     return "web-react"
    return "other"


# ---------- fix implementations (each returns (applied: bool, detail: str)) ----------
def _fix_cometchat_creds(ctx) -> tuple[bool, str]:
    """UC1 F-mobile-creds: the app baked the .env.example placeholder appId → real-time socket dials a
    dead host. Inject the real provisioned creds for this stack before build."""
    fam, env_file = ctx.get("family"), ctx.get("env_file")
    if not env_file or not os.path.exists(os.path.expanduser(env_file)):
        return False, "no env_file"
    from lib import cometchat
    cfg = cometchat._cfg(env_file)
    if fam == "rn" and ctx.get("mobile_dir"):
        from lib import mobile
        return (mobile.write_cometchat_env(Path(ctx["mobile_dir"]), cfg), "rn: wrote EXPO_PUBLIC_COMETCHAT_* to mobile/.env")
    if fam == "flutter" and ctx.get("comp_dir"):
        # Flutter reads creds via --dart-define OR a generated config. Write a dart-define file the
        # build recipe sources, plus a lib/cometchat_config.dart fallback.
        app = Path(ctx["comp_dir"])
        (app / ".dart_define.json").write_text(
            '{"COMETCHAT_APP_ID":"%s","COMETCHAT_REGION":"%s","COMETCHAT_AUTH_KEY":"%s"}'
            % (cfg.get("COMETCHAT_APP_ID", ""), cfg.get("COMETCHAT_REGION", "us"), cfg.get("COMETCHAT_AUTH_KEY", "")))
        return True, "flutter: wrote .dart_define.json (pass --dart-define-from-file at build)"
    return False, f"no creds recipe for family={fam}"


def _fix_cleartext(ctx) -> tuple[bool, str]:
    """UC1: release builds block cleartext HTTP to the local backend. Allow it (Android manifest + iOS ATS)."""
    fam = ctx.get("family")
    if fam == "rn" and ctx.get("mobile_dir"):
        from lib import mobile
        mobile.enable_cleartext(Path(ctx["mobile_dir"])); return True, "rn: usesCleartextTraffic + iOS ATS"
    if fam == "flutter" and ctx.get("comp_dir"):
        app = Path(ctx["comp_dir"]); done = []
        man = app / "android/app/src/main/AndroidManifest.xml"
        if man.exists():
            t = man.read_text()
            # (1) INTERNET permission — THE release-only blocker. Flutter only injects INTERNET into the
            # DEBUG manifest (for hot-reload), so a `flutter build apk --release` ships with NO network
            # access → every HTTP call fails as a generic "Connection error". Add it to the MAIN manifest.
            if "android.permission.INTERNET" not in t:
                nt = re.sub(r"(<manifest\b[^>]*>)",
                            r'\1\n    <uses-permission android:name="android.permission.INTERNET"/>', t, count=1)
                if nt != t:
                    t = nt; done.append("INTERNET permission")
            # (2) cleartext: usesCleartextTraffic on <application> can be overridden by the platform's
            # default network-security-config on some images, so ALSO ship an explicit config that permits
            # cleartext and reference it. Belt-and-suspenders for local HTTP backends in release builds.
            if "usesCleartextTraffic" not in t:
                nt = re.sub(r"<application\b", '<application android:usesCleartextTraffic="true"', t, count=1)
                if nt != t:
                    t = nt; done.append("usesCleartextTraffic")
            if "networkSecurityConfig" not in t:
                nsc = app / "android/app/src/main/res/xml/network_security_config.xml"
                nsc.parent.mkdir(parents=True, exist_ok=True)
                nsc.write_text('<?xml version="1.0" encoding="utf-8"?>\n<network-security-config>\n'
                               '    <base-config cleartextTrafficPermitted="true">\n'
                               '        <trust-anchors><certificates src="system" /></trust-anchors>\n'
                               '    </base-config>\n</network-security-config>\n')
                nt = re.sub(r"<application\b",
                            '<application android:networkSecurityConfig="@xml/network_security_config"', t, count=1)
                if nt != t:
                    t = nt; done.append("networkSecurityConfig")
            man.write_text(t)
        for plist in app.glob("ios/Runner/Info.plist"):
            pb = "/usr/libexec/PlistBuddy"
            subprocess.run([pb, "-c", "Add :NSAppTransportSecurity dict", str(plist)], capture_output=True)
            subprocess.run([pb, "-c", "Add :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true", str(plist)], capture_output=True)
            subprocess.run([pb, "-c", "Set :NSAppTransportSecurity:NSAllowsArbitraryLoads true", str(plist)], capture_output=True)
            done.append("ios ATS")
        return (bool(done), "flutter: " + ", ".join(done) if done else "flutter: no native dirs yet")
    return False, f"no cleartext recipe for family={fam}"


def _fix_jdk17(ctx) -> tuple[bool, str]:
    """gradle/kotlin need JDK 17-21. A too-new JDK fails two ways: 'Unsupported class file major version'
    (older-kotlin path) OR 'IllegalArgumentException: <ver>' from Kotlin's JavaVersion.parse when the
    major is unknown (e.g. Java 26). Pin JAVA_HOME for the re-gate AND persist org.gradle.java.home in the
    android project's gradle.properties, so later rebuilds (demo boot-2, post-integrate) heal too."""
    from lib import mobile
    jdk = mobile.JDK17 if os.path.isdir(mobile.JDK17) else _discover_jdk()
    if not jdk:
        return False, "no compatible JDK (17-21) found — install one (brew install openjdk@17)"
    ctx.setdefault("env", {})["JAVA_HOME"] = jdk
    app = Path(ctx.get("comp_dir") or ctx.get("mobile_dir") or "")
    if (app / "gradlew").exists() or (app / "settings.gradle").exists() or (app / "settings.gradle.kts").exists():
        gp = app / "gradle.properties"
        txt = gp.read_text() if gp.exists() else ""
        if "org.gradle.java.home" not in txt:
            with gp.open("a") as f:
                f.write(f"\norg.gradle.java.home={jdk}\n")
    return True, f"JDK={jdk} (JAVA_HOME + org.gradle.java.home)"


def _discover_jdk() -> str | None:
    """Find a JDK whose major version is 17-21 (android/kotlin-safe). java_home falls back to the newest
    installed JDK, so we validate the actual version rather than trusting it."""
    cands = [
        "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home",
        "/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home",
        "/Applications/Android Studio.app/Contents/jbr/Contents/Home",
        os.path.expanduser("~/Applications/Android Studio.app/Contents/jbr/Contents/Home"),
    ]
    for home in cands:
        rel = Path(home) / "release"
        if rel.exists():
            m = re.search(r'JAVA_VERSION="(\d+)', rel.read_text())
            if m and 17 <= int(m.group(1)) <= 21:
                return home
    return None


def _fix_android_sdk(ctx) -> tuple[bool, str]:
    """android gradle build needs the SDK location (ANDROID_HOME / sdk.dir). Codegen scaffolds rarely
    write local.properties (it's machine-specific + normally git-ignored), so a fresh checkout fails with
    'SDK location not found'. Write sdk.dir from ANDROID_HOME / the default macOS SDK path."""
    app = Path(ctx.get("comp_dir") or ctx.get("mobile_dir") or "")
    if not ((app / "gradlew").exists() or (app / "settings.gradle").exists() or (app / "settings.gradle.kts").exists()):
        return False, "not an android/gradle project"
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") \
        or os.path.expanduser("~/Library/Android/sdk")
    if not os.path.isdir(sdk):
        return False, "Android SDK not found (set ANDROID_HOME)"
    lp = app / "local.properties"
    txt = lp.read_text() if lp.exists() else ""
    if "sdk.dir" not in txt:
        with lp.open("a") as f:
            f.write(f"\nsdk.dir={sdk}\n")
    return True, f"sdk.dir={sdk}"


def _fix_call_permissions(ctx) -> tuple[bool, str]:
    """CometChat voice/video needs native camera+mic (and iOS VoIP background modes). Codegen that places
    the call buttons routinely omits the native permission declarations, so iOS silently fails (button
    inert / incoming accept → immediately 'rejected' because the media session can't open) and android
    can't capture media. Add them — ONLY when the app actually uses calls."""
    app = Path(ctx.get("comp_dir") or ctx.get("mobile_dir") or "")
    if not app.exists():
        return False, "no app dir"
    lib = app / "lib"
    uses_calls = lib.exists() and any(
        re.search(r"CometChatCallButtons|cometchat_calls|CometChatUIKitCalls|CometChatIncomingCall|enableCalls",
                  p.read_text(errors="ignore")) for p in lib.rglob("*.dart"))
    if not uses_calls:
        return False, "app does not use calls — no permissions needed"
    done = []
    # iOS Info.plist — usage descriptions (accessing camera/mic WITHOUT these makes iOS fail the call)
    pb = "/usr/libexec/PlistBuddy"
    for plist in app.glob("ios/Runner/Info.plist"):
        t = plist.read_text(errors="ignore")
        if "NSCameraUsageDescription" not in t:
            subprocess.run([pb, "-c", "Add :NSCameraUsageDescription string 'Camera is used for video calls.'", str(plist)], capture_output=True)
            done.append("ios NSCameraUsageDescription")
        if "NSMicrophoneUsageDescription" not in t:
            subprocess.run([pb, "-c", "Add :NSMicrophoneUsageDescription string 'Microphone is used for voice and video calls.'", str(plist)], capture_output=True)
            done.append("ios NSMicrophoneUsageDescription")
        if "UIBackgroundModes" not in t:
            subprocess.run([pb, "-c", "Add :UIBackgroundModes array", str(plist)], capture_output=True)
            for i, mode in enumerate(("audio", "voip", "remote-notification")):
                subprocess.run([pb, "-c", f"Add :UIBackgroundModes:{i} string {mode}", str(plist)], capture_output=True)
            done.append("ios UIBackgroundModes")
    # Android manifest — camera/mic + foreground-service perms for the calling service
    man = app / "android/app/src/main/AndroidManifest.xml"
    if man.exists():
        t = man.read_text()
        perms = ["android.permission.CAMERA", "android.permission.RECORD_AUDIO",
                 "android.permission.MODIFY_AUDIO_SETTINGS", "android.permission.BLUETOOTH",
                 "android.permission.FOREGROUND_SERVICE", "android.permission.FOREGROUND_SERVICE_MICROPHONE",
                 "android.permission.FOREGROUND_SERVICE_CAMERA", "android.permission.POST_NOTIFICATIONS"]
        add = "".join(f'\n    <uses-permission android:name="{p}"/>' for p in perms if p not in t)
        if add:
            nt = re.sub(r"(<manifest\b[^>]*>)", r"\1" + add, t, count=1)
            if nt != t:
                man.write_text(nt); done.append(f"android {sum(1 for p in perms if p not in t)} call perms")
    return (bool(done), "call perms → " + ", ".join(done) if done else "already present")


def _fix_ios_deploy_target(ctx) -> tuple[bool, str]:
    """The CometChat Flutter Calls SDK (cometchat_calls_sdk) needs iOS deployment target >= 15.1, but a
    fresh Flutter app targets 13.0 → `pod install` fails ('requires a higher minimum iOS deployment
    version'). Bump the Podfile `platform :ios`, force it on every pod via post_install, and raise the
    Xcode project's IPHONEOS_DEPLOYMENT_TARGET. Idempotent."""
    d = ctx.get("comp_dir") or ctx.get("mobile_dir")
    if not d:
        return False, "no dir"
    ios = Path(d) / "ios"
    pod = ios / "Podfile"
    if not pod.exists():
        return False, "no ios/Podfile"
    changed = []
    t = pod.read_text()
    if re.search(r"platform :ios, ['\"]15\.[1-9]", t) is None:
        if re.search(r"^\s*#?\s*platform :ios", t, re.M):
            t = re.sub(r"^\s*#?\s*platform :ios.*$", "platform :ios, '15.1'", t, count=1, flags=re.M)
        else:
            t = "platform :ios, '15.1'\n" + t
        changed.append("Podfile platform")
    if "IPHONEOS_DEPLOYMENT_TARGET'] = '15.1'" not in t:
        hook = ("\npost_install do |installer|\n"
                "  installer.pods_project.targets.each do |target|\n"
                "    flutter_additional_ios_build_settings(target) if defined?(flutter_additional_ios_build_settings)\n"
                "    target.build_configurations.each do |config|\n"
                "      config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '15.1'\n"
                "    end\n  end\nend\n")
        if re.search(r"post_install do", t):   # already has a post_install → inject the setting into it
            t = re.sub(r"(post_install do \|installer\|\n)",
                       r"\1  installer.pods_project.targets.each { |tt| tt.build_configurations.each { |c| "
                       r"c.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '15.1' } }\n", t, count=1)
        else:
            t = t + hook
        changed.append("post_install deployment target")
    pod.write_text(t)
    # Xcode project fallback (Runner target) — set any lower IPHONEOS_DEPLOYMENT_TARGET to 15.1
    pbx = ios / "Runner.xcodeproj" / "project.pbxproj"
    if pbx.exists():
        pt = pbx.read_text()
        npt = re.sub(r"IPHONEOS_DEPLOYMENT_TARGET = 1[0-4]\.[0-9];",
                     "IPHONEOS_DEPLOYMENT_TARGET = 15.1;", pt)
        if npt != pt:
            pbx.write_text(npt); changed.append("pbxproj target")
    subprocess.run(["rm", "-rf", str(ios / "Podfile.lock"), str(ios / "Pods")], capture_output=True)
    return (bool(changed), "ios deploy target → 15.1 (" + ", ".join(changed) + ")" if changed else "already 15.1")


def _fix_gradle_stale(ctx) -> tuple[bool, str]:
    """UC1: 'Could not read workspace metadata' after a cache wipe → stop daemon + clean."""
    d = ctx.get("comp_dir") or ctx.get("mobile_dir")
    if not d:
        return False, "no dir"
    for sub in (Path(d), Path(d) / "android"):
        if (sub / "gradlew").exists():
            subprocess.run(["./gradlew", "--stop"], cwd=str(sub), capture_output=True, timeout=120)
            return True, "gradle --stop (fresh build will re-init)"
    return False, "no gradlew"


def _fix_pod_modular(ctx) -> tuple[bool, str]:
    """UC1: Swift CometChat pod needs modular headers for SPTPersistentCache/DVAssetLoaderDelegate."""
    d = ctx.get("mobile_dir") or ctx.get("comp_dir")
    pod = next(Path(d).glob("ios/Podfile"), None) if d else None
    if not pod:
        return False, "no Podfile"
    t = pod.read_text()
    if "SPTPersistentCache" in t and ":modular_headers" in t:
        return False, "already patched"
    inject = ("  pod 'SPTPersistentCache', :modular_headers => true\n"
              "  pod 'DVAssetLoaderDelegate', :modular_headers => true\n")
    pod.write_text(re.sub(r"(target ['\"][^'\"]+['\"] do\n)", r"\1" + inject, t, count=1))
    return True, "added targeted modular_headers to Podfile"


_STARSCREAM_PODSPEC = """Pod::Spec.new do |s|
  s.name = 'CometChatStarscream'
  s.version = '1.0.2'
  s.summary = 'CometChat fork of Starscream (WebSocket) — companion module CometChatSDK imports but does NOT bundle'
  s.homepage = 'https://www.cometchat.com'
  s.license = { :type => 'Commercial', :text => 'CometChat' }
  s.author = 'CometChat'
  s.platform = :ios, '13.0'
  s.source = { :http => 'https://library.cometchat.io/ios/v4.0/xcode15/CometChatStarscream_1_0_2.xcframework.zip' }
  s.vendored_frameworks = 'CometChatStarscream.xcframework'
end
"""


def _ios_companion_podfiles(ctx) -> list[Path]:
    """Every iOS Podfile under this component that pulls in CometChatUIKitSwift — the native app's own
    `ios/Podfile` (or a Podfile at the dir root, as with a native Swift app) AND the Flutter/RN-managed
    `ios/Podfile`. Only Podfiles that actually reference the UIKit pod need the companion modules."""
    seen: set[Path] = set()
    out: list[Path] = []
    for key in ("comp_dir", "mobile_dir", "repo_dir"):
        d = ctx.get(key)
        if not d:
            continue
        base = Path(d)
        for pf in [base / "Podfile", *base.glob("ios/Podfile"), *base.glob("*/ios/Podfile")]:
            if pf.exists() and pf not in seen:
                seen.add(pf)
                try:
                    if "CometChatUIKitSwift" in pf.read_text():
                        out.append(pf)
                except Exception:
                    pass
    return out


def _fix_ios_companion_pods(ctx) -> tuple[bool, str]:
    """I7 (recurring gap): CometChatSDK 4.1.x `import`s CometChatStarscream (its WebSocket lib) and
    CometChatUIKitSwift 5.1.x `import`s CometChatCardsSwift, but the published pods REFERENCE these
    companion modules without bundling/declaring them → a by-the-book `pod install` yields a target that
    can't compile ("no such module 'CometChatStarscream' / 'CometChatCardsSwift'"). Add both explicitly:
    CometChatStarscream 1.0.2 via a local podspec pointing at CometChat's CDN xcframework, and
    CometChatCardsSwift '~> 1.1' (a normally-published pod that isn't pulled transitively). NOT SPM,
    NOT an Xcode/Swift-version issue. Runs BEFORE `pod install`, so the build never hits I7."""
    pods = _ios_companion_podfiles(ctx)
    if not pods:
        return False, "no CometChatUIKitSwift Podfile found"
    inject = ("  pod 'CometChatStarscream', :podspec => 'CometChatStarscream.podspec'  # I7: companion module, not bundled by the SDK pod\n"
              "  pod 'CometChatCardsSwift', '~> 1.1'                                    # I7: companion module, not pulled transitively\n")
    patched = 0
    for pf in pods:
        t = pf.read_text()
        if "CometChatStarscream" in t and "CometChatCardsSwift" in t:
            continue  # both companions already declared — nothing to do
        (pf.parent / "CometChatStarscream.podspec").write_text(_STARSCREAM_PODSPEC)
        # Place them right after the UIKit pod (same target); fall back to the first target block.
        m = re.search(r"^[ \t]*pod ['\"]CometChatUIKitSwift['\"].*\n", t, re.MULTILINE)
        if m:
            t = t[:m.end()] + inject + t[m.end():]
        else:
            t = re.sub(r"(target ['\"][^'\"]+['\"] do\n)", r"\1" + inject, t, count=1)
        pf.write_text(t)
        patched += 1
    if not patched:
        return False, "companion pods already declared"
    return True, f"added CometChatStarscream(podspec)+CometChatCardsSwift to {patched} Podfile(s)"


_MAVEN_BUILDER = "maven:3.9-eclipse-temurin-17"


def _fix_java_dockerfile_multistage(ctx) -> tuple[bool, str]:
    """Make a Java backend image build its own jar instead of COPYing a host-built one.

    Codegen emits `FROM eclipse-temurin:17-jre-jammy` + `COPY target/<app>.jar app.jar`, which means
    the image contains whatever jar happened to be on the host at build time. Nothing in the pipeline
    re-runs `mvn package` after integrate, so `docker compose up --build` faithfully re-copies STALE
    bytecode: on fin the running backend predated the CometChat integration entirely (zero CometChat
    classes in the jar), so login returned an empty cometchat_auth_token and verify's
    "login mints no CometChat token" gate fired — pointing at the login code, which was correct.
    It also means the repo cannot be built from a fresh clone at all, since target/ is git-ignored.
    Rewrite to a multi-stage build so the image always matches the source."""
    repo = Path(ctx.get("repo_dir") or "")
    out = []
    for df in [repo / "backend" / "Dockerfile", repo / "Dockerfile"]:
        if not df.exists():
            continue
        t = df.read_text()
        if "AS builder" in t or "as builder" in t:
            continue                                  # already multi-stage
        m = re.search(r"^\s*COPY\s+(?:--chown=\S+\s+)?target/\S*\.jar\s+(\S+)\s*$", t, re.M)
        if not m:
            continue                                  # not the copy-a-prebuilt-jar shape
        if not (df.parent / "pom.xml").exists():
            continue                                  # only Maven projects
        dest = m.group(1)
        builder = (f"FROM {_MAVEN_BUILDER} AS builder\n"
                   "WORKDIR /build\n"
                   "COPY pom.xml .\n"
                   "RUN mvn -B -q dependency:go-offline\n"
                   "COPY src ./src\n"
                   "RUN mvn -B -q package -DskipTests\n\n")
        t = builder + t[:m.start()] + f"COPY --from=builder /build/target/*.jar {dest}\n" + t[m.end():]
        df.write_text(t)
        out.append(str(df.relative_to(repo)))
    if not out:
        return False, "no single-stage Java Dockerfile copying a prebuilt jar"
    return True, f"multi-stage Maven build → {out} (image now compiles the CURRENT source)"


def _fix_ios_calls_sdk_version(ctx) -> tuple[bool, str]:
    """The iOS Calls SDK on the 4.x line (what `~> 4.1` resolves to — 4.2.3) HARD-CRASHES the instant the
    in-call session UI mounts on an iOS 26 simulator: EXC_BAD_ACCESS (SIGSEGV, "possible pointer
    authentication failure") inside CometChatCallsSDK → facebook::react::invokeInner — the React-Native
    bridge embedded in the Calls SDK dying in the unwinder. Placement/ringing/signaling and WebRTC media all
    work; ONLY the session screen dies (white screen → crash). Crashes identically on arm64 sim and
    x86_64-under-Rosetta, so it is not arch alone. FIX: pin `~> 5.0` (→ 5.0.1), which stays compatible with
    CometChatSDK 4.1.6 / CometChatUIKitSwift 5.1.16 — the widely-held "4.2.3 is the newest CallsSDK
    compatible with the 4.1.x line" belief is FALSE. HONESTY: 5.0.1 STILL embeds React Native (RCTBridge
    present); this is an EMPIRICAL fix (5.0.1's RN build doesn't trip the PAC/unwinder fault on iOS 26,
    4.2.3 does), NOT "5.x removed RN". Runs BEFORE `pod install` so no iOS use case ever hits the crash."""
    pods = _ios_companion_podfiles(ctx)
    if not pods:
        return False, "no CometChatUIKitSwift Podfile found"
    patched, added = 0, 0
    for pf in pods:
        t = pf.read_text()
        if not re.search(r"pod\s+['\"]CometChatCallsSDK['\"]", t):
            # NO CometChatCallsSDK pod at all. The comment this replaced claimed "absent/unpinned
            # already resolves to the 5.x line" — that is WRONG: absent means the pod is never
            # installed, so the calls ENGINE is simply not linked. The calling UI still renders (the
            # incoming-call banner appears, which reads as "calls work"), but CometChat.initiateCall
            # fails at runtime with "Framework not installed please install" and no call is ever
            # placed. Observed on fin, where integrate codegen emitted a Podfile with only
            # CometChatUIKitSwift — so the version-bump branch below had nothing to bump and the fix
            # silently no-op'd. ADD the pod at the pinned 5.0 line.
            line = ("  pod 'CometChatCallsSDK', '~> 5.0'   "
                    "# calls ENGINE — without it initiateCall fails 'Framework not installed'\n")
            m = re.search(r"^[ \t]*pod ['\"]CometChatUIKitSwift['\"].*\n", t, re.MULTILINE)
            if not m:
                continue
            pf.write_text(t[:m.end()] + line + t[m.end():])
            added += 1
            continue
        # An explicit 4.x pin crashes the in-call UI on iOS 26 → bump it to the 5.0 line.
        new = re.sub(r"(pod\s+['\"]CometChatCallsSDK['\"]\s*,\s*)['\"](?:~>\s*)?4[\d.]*['\"]",
                     r"\1'~> 5.0'", t)
        if new != t:
            pf.write_text(new)
            patched += 1
    if added:
        return True, (f"ADDED CometChatCallsSDK '~> 5.0' to {added} Podfile(s) (was absent → calls engine "
                      f"unlinked)" + (f"; bumped 4.x in {patched}" if patched else ""))
    if patched:
        return True, f"pinned CometChatCallsSDK '~> 5.0' (was 4.x) in {patched} Podfile(s)"
    # Present and ALREADY on the 5.0 line: nothing to change, but the guard IS satisfied for this
    # native-iOS + calls stack, so report success so the SDK-gap WITNESS is still recorded. The 4.x
    # in-call crash is why the pin must be here, whether we, codegen, or a prior run put it there —
    # an idempotent-satisfied guard that returned False here silently dropped a real, recurring gap
    # from the ledger (the "self-heal forgot to add the repeating gap" bug).
    if any(re.search(r"pod\s+['\"]CometChatCallsSDK['\"]\s*,\s*['\"](?:~>\s*)?5[\d.]*['\"]", pf.read_text())
           for pf in pods):
        return True, "CometChatCallsSDK already pinned to the 5.0 line (workaround present)"
    return False, "CometChatCallsSDK present but not on 4.x or 5.x (nothing to do)"


# The bundle keys Xcode auto-injects ONLY when GENERATE_INFOPLIST_FILE=YES. A project that points
# INFOPLIST_FILE at a hand-written plist gets none of them.
_IOS_PLIST_REQUIRED = {
    "CFBundleIdentifier": "$(PRODUCT_BUNDLE_IDENTIFIER)",
    "CFBundleExecutable": "$(EXECUTABLE_NAME)",
    "CFBundleName": "$(PRODUCT_NAME)",
    "CFBundlePackageType": "APPL",
    "CFBundleInfoDictionaryVersion": "6.0",
    "CFBundleShortVersionString": "1.0",
    "CFBundleVersion": "1",
    "CFBundleDevelopmentRegion": "$(DEVELOPMENT_LANGUAGE)",
}


def ensure_ios_infoplist_keys(comp_dir) -> list[dict]:
    """Guarantee the built .app carries a bundle identifier.

    A native-iOS project that sets a CUSTOM `INFOPLIST_FILE` WITHOUT `GENERATE_INFOPLIST_FILE = YES`
    gets no auto-injected bundle keys, so the built .app ships with NO CFBundleIdentifier and is
    UNINSTALLABLE — `simctl install` fails "Missing bundle ID" (IXErrorDomain code 13) on every
    simulator and device. The build still exits 0, so this passes the compile gate and only shows up as
    a home-screen screenshot at demo time. Injects the keys Xcode would have generated, using the same
    $(VAR) macros so PRODUCT_BUNDLE_IDENTIFIER stays the single source of truth."""
    import plistlib
    d = Path(comp_dir)
    proj = next(iter(sorted(d.glob("*.xcodeproj"))), None)
    if proj is None:
        return []
    pbx = (proj / "project.pbxproj")
    txt = pbx.read_text() if pbx.exists() else ""
    if re.search(r"GENERATE_INFOPLIST_FILE\s*=\s*YES", txt):
        return []                                   # Xcode generates them; nothing to do
    m = re.search(r"INFOPLIST_FILE\s*=\s*\"?([^\";\n]+)\"?\s*;", txt)
    if not m:
        return []
    plist = d / m.group(1).strip()
    if not plist.exists():
        return []
    try:
        data = plistlib.loads(plist.read_bytes())
    except Exception:
        return []
    missing = {k: v for k, v in _IOS_PLIST_REQUIRED.items() if k not in data}
    if not missing:
        return []
    data.update(missing)
    plist.write_bytes(plistlib.dumps(data))
    return [{"rule": "ios-infoplist-bundle-keys", "owner": "harness",
             "detail": f"injected {sorted(missing)} into {plist.name} "
                       f"(custom INFOPLIST_FILE without GENERATE_INFOPLIST_FILE)"}]


def ensure_ios_companion_pods(comp_dir, slug: str | None = None) -> list[dict]:
    """Proactive entry point the iOS build gate calls BEFORE `pod install`. Runs the I7 companion-pods
    guard for a native-iOS component and records the gap (self-heal witnesses it). Returns applied fixes."""
    d = Path(comp_dir)
    return preapply({"stage": "build", "family": "ios-native", "comp_dir": str(d),
                     "mobile_dir": str(d), "repo_dir": str(d.parent),
                     "slug": slug or d.parent.name, "integrated": False})


_CALL_CSS_VARS = """
/* CometChat calls-SDK gap (self-heal): the video-tile grid is sized with an inline
   height: calc(100% - var(--cometchat-calls-call-footer-height) - var(--cometchat-calls-call-header-height))
   but the SDK references those two custom properties and NEVER defines them. An undefined var() in calc()
   is invalid at computed-value time → height computes to 0px → the ongoing-call grid collapses → the SDK's
   ResizeObserver throws "Container dimensions and number of tiles must be positive" and the call renders
   collapsed. Defining the vars makes the calc resolve to a positive height. */
:root {
  --cometchat-calls-call-header-height: 60px;
  --cometchat-calls-call-footer-height: 80px;
}
"""

# Global-stylesheet conventions across the web frameworks the pipeline emits (Angular/React/Vue/Next/…).
_WEB_GLOBAL_STYLES = [
    "src/styles.scss", "src/styles.sass", "src/styles.css",
    "app/globals.css", "src/app/globals.css", "styles/globals.css",
    "src/index.scss", "src/index.css", "src/style.css", "src/global.css", "src/assets/main.css",
]


def _fix_web_call_css_vars(ctx) -> tuple[bool, str]:
    """The CometChat web **calls** SDK (@cometchat/calls-sdk-javascript) sizes its tile grid with an inline
    height:calc() referencing --cometchat-calls-call-{header,footer}-height, which it never defines →
    invalid calc → 0px grid → ResizeObserver throws "Container dimensions and number of tiles must be
    positive" (verified: undefined-var calc computes to 0px; defined → 674px). Define the two vars in the
    web app's global stylesheet so the ongoing-call surface lays out instead of collapsing."""
    d = ctx.get("comp_dir")
    if not d:
        return False, "no comp_dir"
    comp = Path(d)
    pj = comp / "package.json"
    try:
        if "calls-sdk-javascript" not in pj.read_text():
            return False, "no @cometchat/calls-sdk-javascript dep (calls not integrated)"
    except Exception:
        return False, "no package.json"
    styles = next((comp / rel for rel in _WEB_GLOBAL_STYLES if (comp / rel).exists()), None)
    if not styles:
        return False, "no global stylesheet found"
    t = styles.read_text()
    if "--cometchat-calls-call-header-height" in t:
        return False, "call css vars already defined"
    styles.write_text(t.rstrip() + "\n" + _CALL_CSS_VARS)
    return True, f"defined call-height CSS vars in {styles.relative_to(comp)}"


def ensure_web_call_css_vars(comp_dir, slug: str | None = None) -> list[dict]:
    """Proactive entry point the WEB build gate calls before building — defines the two CSS vars the calls
    SDK references-but-never-defines, and records the SDK gap. Returns applied fixes."""
    d = Path(comp_dir)
    return preapply({"stage": "build", "family": "web", "comp_dir": str(d), "repo_dir": str(d.parent),
                     "slug": slug or d.parent.name, "integrated": False})


def _fix_expo_android_splash(ctx) -> tuple[bool, str]:
    """RN/Expo prebuild emits res/drawable/splashscreen.xml referencing @color/splashscreen_background, but
    the generated res/values/colors.xml frequently OMITS that color → release `assembleRelease` dies at
    resource-linking with "Android resource linking failed: resource color/splashscreen_background not
    found" (a plain debug/JS build passes, so it only surfaces on the release APK the demo builds). Define
    the missing color (idempotent) so the splash drawable resolves. Codegen/app gap, not a CometChat one."""
    d = ctx.get("comp_dir")
    if not d:
        return False, "no comp_dir"
    res = Path(d) / "android" / "app" / "src" / "main" / "res"
    drawable = res / "drawable" / "splashscreen.xml"
    colors = res / "values" / "colors.xml"
    try:
        if not drawable.exists() or "splashscreen_background" not in drawable.read_text():
            return False, "no splashscreen_background reference (nothing to fix)"
    except Exception:
        return False, "could not read splashscreen.xml"
    line = '  <color name="splashscreen_background">#ffffff</color>\n'
    if colors.exists():
        t = colors.read_text()
        if "splashscreen_background" in t:
            return False, "splashscreen_background already defined"
        t = t.replace("</resources>", line + "</resources>") if "</resources>" in t \
            else t.rstrip() + "\n<resources>\n" + line + "</resources>\n"
        colors.write_text(t)
    else:
        colors.parent.mkdir(parents=True, exist_ok=True)
        colors.write_text("<resources>\n" + line + "</resources>\n")
    return True, "defined splashscreen_background in android colors.xml"


def ensure_expo_android_splash(comp_dir, slug: str | None = None) -> list[dict]:
    """Proactive entry point the RN android build calls before `assembleRelease` — defines the splash color
    the expo prebuild references-but-omits, so resource linking doesn't fail. comp_dir = the mobile dir."""
    d = Path(comp_dir)
    return preapply({"stage": "build", "family": "rn", "comp_dir": str(d), "repo_dir": str(d.parent),
                     "slug": slug or d.parent.name, "integrated": False})


_WEB_CC_KEYS = ("COMETCHAT_APP_ID", "COMETCHAT_REGION", "COMETCHAT_AUTH_KEY")
# EXPO_PUBLIC_ covers React Native / Expo (mobile) — same build-time-inlined-cred gap as web: the RN app
# reads process.env.EXPO_PUBLIC_COMETCHAT_APP_ID, and if mobile/.env is missing/empty CometChat init hangs
# (the Conversations list spins forever). Validated on dat: mobile/.env didn't exist (only .env.example
# held the real creds) → CometChat never logged in until .env was seeded.
_WEB_ENV_PREFIXES = ("VITE_", "NEXT_PUBLIC_", "REACT_APP_", "EXPO_PUBLIC_")


def _cc_placeholder(v: str) -> bool:
    v = (v or "").strip()
    return (not v) or ("your" in v.lower()) or ("here" in v.lower()) or v in ("changeme", "xxx", "app-id")


def _fix_web_cometchat_creds(ctx) -> tuple[bool, str]:
    """The web build (Vite/Next/CRA) INLINES CometChat creds at build time from prefixed env vars
    (VITE_/NEXT_PUBLIC_/REACT_APP_ COMETCHAT_APP_ID). provision writes the real APP_ID to
    <slug>/.env.cometchat and compose-env feeds the BACKEND, but the web comp's .env is scaffolded with an
    EMPTY/placeholder *_COMETCHAT_APP_ID → the SDK init throws "Missing VITE_COMETCHAT_APP_ID" and NO chat
    or call ever works (the web BUILD-time creds are the gap — backend + mobile are covered elsewhere).
    Fill any empty/placeholder *_COMETCHAT_{APP_ID,REGION,AUTH_KEY} key the web .env ALREADY declares, from
    the provisioned env. Idempotent; never invents keys the app doesn't read."""
    comp = ctx.get("comp_dir"); env_file = ctx.get("env_file")
    if not comp or not env_file:
        return False, "no comp_dir/env_file"
    comp = Path(comp); web_env = comp / ".env"
    if not web_env.exists():
        ex = comp / ".env.example"
        if not ex.exists():
            return False, "no web .env or .env.example"
        web_env.write_text(ex.read_text())     # seed declared keys so they can be filled
    prov = {}
    try:
        for ln in Path(env_file).read_text().splitlines():
            ln = ln.strip()
            if "=" in ln and not ln.startswith("#"):
                k, v = ln.split("=", 1); prov[k.strip()] = v.strip()
    except Exception:
        return False, "could not read provisioned env"
    lines = web_env.read_text().splitlines(); changed = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1); k = k.strip()
        for pref in _WEB_ENV_PREFIXES:
            for cc in _WEB_CC_KEYS:
                if k == pref + cc and _cc_placeholder(v) and not _cc_placeholder(prov.get(cc, "")):
                    lines[i] = f"{k}={prov[cc]}"; changed.append(k)
    if not changed:
        return False, "web cometchat creds already populated"
    web_env.write_text("\n".join(lines) + "\n")
    return True, f"filled web build-time creds: {', '.join(changed)}"


def ensure_web_cometchat_creds(comp_dir, env_file, slug: str | None = None) -> list[dict]:
    """Proactive entry point verify calls before compose_up --build — fills the web comp's build-time
    CometChat creds from the provisioned env so the SDK can init. comp_dir = the web comp dir."""
    d = Path(comp_dir)
    return preapply({"stage": "verify", "family": "web", "comp_dir": str(d), "repo_dir": str(d.parent),
                     "env_file": str(env_file), "slug": slug or d.parent.name, "integrated": True})


def _fix_disk(ctx) -> tuple[bool, str]:
    """Reclaim disk (UC1 filled it and crashed Docker). Prune build transients."""
    from lib import mobile
    mobile.cleanup_build_artifacts(Path(ctx["mobile_dir"]) if ctx.get("mobile_dir") else None)
    return True, f"pruned transients; free={mobile.disk_free_gb()}GB"


def _fix_compose_env(ctx) -> tuple[bool, str]:
    """Integrate wires the backend CODE to mint a CometChat auth token (reads env('COMETCHAT_APP_ID')
    etc.), but docker-compose passes NONE of those creds to the backend container → the mint bails to an
    empty token → the app skips CometChat login → the conversation list errors ("Oops") on EVERY client.
    Inject `${VAR}` REFERENCES into the backend `environment:` block and put the real VALUES in a
    git-ignored `.env` (docker-compose's default interpolation file) — so live secrets never land in the
    TRACKED compose file (the pre-push secret scan would rightly block that). Emits BOTH REST-key names
    (COMETCHAT_REST_KEY and COMETCHAT_REST_API_KEY) to absorb the codegen naming drift between them."""
    repo = Path(ctx.get("repo_dir", "")); env_file = ctx.get("env_file")
    comp = repo / "docker-compose.yml"
    if not comp.exists() or not env_file or not os.path.exists(os.path.expanduser(env_file)):
        return False, "no compose / env_file"
    from lib import cometchat
    cfg = cometchat._cfg(env_file)
    appid = cfg.get("COMETCHAT_APP_ID", "")
    if not appid:
        return False, "no COMETCHAT_APP_ID in env_file"
    rest = cfg.get("COMETCHAT_REST_API_KEY", "") or cfg.get("COMETCHAT_REST_KEY", "")
    kv = {"COMETCHAT_APP_ID": appid, "COMETCHAT_REGION": cfg.get("COMETCHAT_REGION", "us"),
          "COMETCHAT_AUTH_KEY": cfg.get("COMETCHAT_AUTH_KEY", ""),
          "COMETCHAT_REST_KEY": rest, "COMETCHAT_REST_API_KEY": rest}
    # 1) VALUES → repo/.env (git-ignored; docker-compose auto-reads it for ${..} interpolation at `up`).
    #    Merge: keep any non-COMETCHAT lines already there, refresh the COMETCHAT_* ones.
    dotenv = repo / ".env"
    keep = []
    if dotenv.exists():
        keep = [ln for ln in dotenv.read_text().splitlines()
                if ln.strip() and not ln.strip().startswith("COMETCHAT_")]
    dotenv.write_text("\n".join(keep + [f"{k}={v}" for k, v in kv.items() if v]) + "\n")
    # 2) REFERENCES (never literal secrets) → the backend service `environment:` block.
    t = comp.read_text()
    if re.search(r'\$\{COMETCHAT_APP_ID', t):
        return False, "compose already references COMETCHAT_* via ${..}"
    t = "\n".join(ln for ln in t.splitlines() if not re.match(r"^\s*COMETCHAT_[A-Z_]+\s*:", ln))
    out, in_backend, svc_indent, done = [], False, -1, False
    for ln in t.splitlines():
        m = re.match(r"^(\s*)([\w-]+):\s*$", ln)          # a "name:" header with no inline value
        if m:
            indent, name = len(m.group(1)), m.group(2)
            if name == "backend" and indent <= 4:
                in_backend, svc_indent = True, indent
            elif in_backend and indent <= svc_indent and name != "backend":
                in_backend = False                         # left the backend service block
        out.append(ln)
        if in_backend and not done and re.match(r"^\s+environment:\s*$", ln):
            ind = (len(ln) - len(ln.lstrip())) + 2         # entries indent one level under environment:
            for k in kv:
                if kv[k]:
                    out.append(" " * ind + f'{k}: "${{{k}:-}}"')   # ${KEY:-} — interpolated from repo/.env
            done = True
    if not done:
        return False, "backend service has no `environment:` block to extend"
    comp.write_text("\n".join(out) + "\n")
    return True, "backend env → ${COMETCHAT_*} refs (values in git-ignored .env; no secrets in tracked compose)"


# The standard Compose experimental markers. `testTagsAsResourceId` (ExperimentalComposeUiApi) is the one
# that actually bites, and the HARNESS ITSELF induces it: the build prompt requires it so Maestro can target
# `id:` in the mobile login flow — so this failure is structural on every Compose use case, not bad luck.
_COMPOSE_OPTINS = ("androidx.compose.ui.ExperimentalComposeUiApi",
                   "androidx.compose.material3.ExperimentalMaterial3Api",
                   "androidx.compose.foundation.ExperimentalFoundationApi",
                   "androidx.compose.animation.ExperimentalAnimationApi")


def _fix_kotlin_optin(ctx) -> tuple[bool, str]:
    """Kotlin fails the build ('This API is experimental and is likely to change in the future') when
    codegen calls an @Experimental* Compose API without @OptIn. Rather than chase every call site, add
    the opt-in markers as MODULE compiler args — which is what real Compose apps do — so the whole
    module compiles regardless of which experimental API codegen reached for."""
    app = Path(ctx.get("comp_dir") or ctx.get("mobile_dir") or "")
    gradle = next((c for c in (app / "app" / "build.gradle.kts", app / "app" / "build.gradle",
                               app / "build.gradle.kts", app / "build.gradle") if c.exists()), None)
    if gradle is None:
        return False, "no module build.gradle(.kts) found"
    txt = gradle.read_text()
    if "-opt-in=androidx.compose" in txt:
        return False, "compose opt-in compiler args already present"
    kts = gradle.suffix == ".kts"
    line = ("        freeCompilerArgs += listOf(" + ", ".join(f'"-opt-in={m}"' for m in _COMPOSE_OPTINS) + ")"
            if kts else
            "        freeCompilerArgs += [" + ", ".join(f"'-opt-in={m}'" for m in _COMPOSE_OPTINS) + "]")
    m = re.search(r"^\s*kotlinOptions\s*\{", txt, re.M)
    if m:
        txt = txt[:m.end()] + "\n" + line + txt[m.end():]
    else:  # no kotlinOptions block yet → open one inside android { }
        m2 = re.search(r"^\s*android\s*\{", txt, re.M)
        if not m2:
            return False, "no kotlinOptions or android { } block to extend"
        txt = txt[:m2.end()] + "\n    kotlinOptions {\n" + line + "\n    }" + txt[m2.end():]
    gradle.write_text(txt)
    return True, f"compose opt-in compiler args → {gradle.name}"


# ---------- rule registry ----------
# phase: 'pre' = proactive before build · 'on_fail' = reactive on a matching failure
RULES = [
    {"id": "java-dockerfile-multistage", "phase": "pre", "families": {"web", "rn", "flutter",
                                                                     "android-native", "ios-native", "other"},
     "sig": r"COPY\s+target/\S*\.jar|cometchat_auth_token|no CometChat auth token",
     "fix": _fix_java_dockerfile_multistage, "owner": "harness",
     "note": "fin: the backend image COPYed a host-built jar, so it ran PRE-integration bytecode "
             "(zero CometChat classes) and login returned an empty cometchat_auth_token"},
    {"id": "kotlin-optin", "phase": "on_fail", "families": {"android-native", "rn"},
     "sig": r"This API is experimental and is likely to change|requires opt-in|Opt-in requirement"
            r"|Experimental(ComposeUi|Material3|Foundation|Animation)Api", "fix": _fix_kotlin_optin,
     "owner": "harness",
     "note": "fin: Compose codegen used testTagsAsResourceId (@ExperimentalComposeUiApi) with no @OptIn → "
             "compileDebugKotlin fails. The harness REQUIRES that property (Maestro id: targeting), so it "
             "owns the fix; not a CometChat skills gap."},
    {"id": "cleartext-http", "phase": "pre", "families": {"rn", "flutter"},
     "sig": r"CLEARTEXT|ERR_CLEARTEXT|App Transport Security|NSAllowsArbitraryLoads", "fix": _fix_cleartext,
     "note": "UC1: release builds block cleartext to the local HTTP backend",
     "owner": "skills",
     "gap": "The mobile native-setup skill must document that a RELEASE build talking to a local HTTP backend "
            "needs android:usesCleartextTraffic + a network_security_config AND the INTERNET permission in the "
            "MAIN manifest (Flutter injects INTERNET only into the DEBUG manifest) + iOS ATS NSAllowsArbitraryLoads."},
    {"id": "jdk17", "phase": "on_fail", "families": {"rn", "flutter", "android-native"},
     "sig": r"Unsupported class file major version|invalid source release|requires Java"
            r"|JavaVersion\.parse|IllegalArgumentException: \d+\.\d+\.\d+|isAtLeastJava", "fix": _fix_jdk17,
     "note": "UC1: gradle needs JDK 17", "owner": "skills",
     "gap": "The core/build skill should pin the JDK/Kotlin floor (JDK 17; Kotlin >=2.2.0 for 6.0.x GA) — a newer "
            "JDK or older Kotlin fails with 'Unsupported class file major version' / 'incompatible metadata version'."},
    {"id": "call-permissions", "phase": "pre", "families": {"rn", "flutter"}, "when_integrated": True,
     "sig": r"NSCameraUsageDescription|NSMicrophoneUsageDescription|RECORD_AUDIO|camera permission|microphone permission",
     "fix": _fix_call_permissions, "owner": "skills",
     "note": "UC2: CometChat calls need native camera/mic (+ iOS VoIP background modes); codegen omits them",
     "gap": "The calls skill should CO-LOCATE the native camera/mic + iOS UIBackgroundModes(audio/voip) "
            "requirement with the CometChatCallButtons usage (or ship it via a config plugin that survives "
            "regeneration) — without NSCamera/NSMicrophoneUsageDescription, iOS calls silently fail: the call "
            "button is inert and an accepted incoming call is immediately 'rejected' (media session can't open)."},
    {"id": "ios-deploy-target", "phase": "pre", "families": {"rn", "flutter"}, "when_integrated": True,
     "sig": r"higher minimum iOS deployment version|IPHONEOS_DEPLOYMENT_TARGET|deployment target to at least",
     "fix": _fix_ios_deploy_target,
     "note": "UC2: cometchat_calls_sdk needs iOS deployment target >= 15.1 (Flutter defaults to 13.0)",
     "owner": "skills",
     "gap": "cometchat-flutter-v6-calls / cometchat-ios must document that cometchat_calls_sdk requires an iOS "
            "deployment target >= 15.1 (Flutter/RN scaffold 13.0) — `pod install` fails 'requires a higher minimum "
            "iOS deployment version' otherwise. Ship the Podfile platform + post_install IPHONEOS_DEPLOYMENT_TARGET."},
    {"id": "gradle-stale", "phase": "on_fail", "families": {"rn", "flutter", "android-native"},
     "sig": r"Could not read workspace metadata|metadata\.bin|corrupt", "fix": _fix_gradle_stale,
     "note": "UC1: stop stale gradle daemon after a cache wipe", "owner": "harness"},
    {"id": "pod-modular", "phase": "on_fail", "families": {"rn", "flutter", "ios-native"},
     "sig": r"does not define modules|SPTPersistentCache|DVAssetLoaderDelegate|use_modular_headers", "fix": _fix_pod_modular,
     "note": "UC1: Swift CometChat pod needs modular headers", "owner": "skills",
     "gap": "The iOS/native skill should ship use_modular_headers! (or targeted modular headers for "
            "SPTPersistentCache / DVAssetLoaderDelegate) via a config plugin that SURVIVES `expo prebuild` "
            "(which regenerates the Podfile) — otherwise `pod install` fails 'does not define modules'."},
    {"id": "web-call-css-vars", "phase": "pre", "families": {"web"},
     "sig": r"Container dimensions and number of tiles must be positive|cometchat-calls-tile-grid",
     "fix": _fix_web_call_css_vars, "owner": "sdk",
     "note": "CometChat calls SDK references --cometchat-calls-call-{header,footer}-height in its grid calc() but never defines them → 0px collapse",
     "gap": "The CometChat web calls SDK (@cometchat/calls-sdk-javascript) sizes its tile-grid <div> with an "
            "INLINE height: calc(100% - var(--cometchat-calls-call-footer-height) - "
            "var(--cometchat-calls-call-header-height)) but references those two custom properties WITHOUT ever "
            "defining them (each appears exactly once — this calc — in the SDK bundle; the UI Kit doesn't define "
            "them either). An undefined var() in calc() is invalid at computed-value time → height computes to 0px "
            "→ the ongoing-call grid collapses → the SDK's ResizeObserver throws \"Container dimensions and number "
            "of tiles must be positive\" and the call renders collapsed (proven: undefined-var calc → 0px, defined "
            "→ 674px). The SDK must define these variables itself, or use fallbacks in the calc (var(--x, 0px)). "
            "Workaround (auto-applied by the web build gate): define both in the app's global stylesheet :root."},
    {"id": "ios-companion-pods", "phase": "pre", "families": {"ios-native", "flutter", "rn"},
     "sig": r"no such module 'CometChatStarscream'|no such module 'CometChatCardsSwift'|CometChatStarscream|CometChatCardsSwift",
     "fix": _fix_ios_companion_pods, "owner": "sdk",
     "note": "I7: CometChat iOS pods reference companion modules (CometChatStarscream/CometChatCardsSwift) without bundling them",
     "gap": "CometChat's iOS pods are shipped-incomplete: CometChatSDK 4.1.x imports CometChatStarscream (its WebSocket "
            "lib) and CometChatUIKitSwift 5.1.x imports CometChatCardsSwift, but a by-the-book `pod install` neither "
            "vends nor declares either — so the target fails to compile with \"no such module 'CometChatStarscream' / "
            "'CometChatCardsSwift'\". The published UIKit/SDK podspecs must declare these as dependencies (or vend the "
            "sub-frameworks). Workaround (auto-applied by the build gate): add CometChatStarscream 1.0.2 via a local "
            "podspec pointing at the CDN xcframework (library.cometchat.io/ios/v4.0/xcode15/"
            "CometChatStarscream_1_0_2.xcframework.zip) + CometChatCardsSwift '~> 1.1'. This is NOT an Xcode/Swift-version "
            "issue and NOT fixable by switching to SPM (empty stubs link but crash at launch: Symbol not found WebSocketEvent)."},
    {"id": "ios-calls-sdk-version", "phase": "pre", "families": {"ios-native", "flutter", "rn"},
     "sig": r"facebook::react::invokeInner|RCTNativeModule::invoke|possible pointer authentication failure|"
            r"EXC_BAD_ACCESS.*CometChatCallsSDK|CometChatCallsSDK.*(SIGSEGV|crash)",
     "fix": _fix_ios_calls_sdk_version, "owner": "sdk",
     "note": "iOS CallsSDK 4.x crashes on in-call UI mount (iOS 26 sim) — pin ~> 5.0",
     "gap": "The CometChat iOS Calls SDK on the 4.x line (`~> 4.1` → 4.2.3) HARD-CRASHES the moment the in-call "
            "session UI mounts on an iOS 26 simulator: EXC_BAD_ACCESS (SIGSEGV, \"possible pointer authentication "
            "failure\") inside CometChatCallsSDK → facebook::react::invokeInner — the React-Native bridge embedded "
            "in the Calls SDK dying in the unwinder during a native-module invoke. Call placement, ringing, "
            "signaling and WebRTC media ALL work (peer holds a live connected call); only the session screen dies "
            "(white screen ~1s → crash). Reproduces identically on the arm64 simulator AND x86_64-under-Rosetta, so "
            "it is not an arm64-PAC issue alone, and it is entirely inside SDK frames (no app code on the stack). "
            "FIX: pin `pod 'CometChatCallsSDK', '~> 5.0'` (resolves 5.0.1) — it stays compatible with CometChatSDK "
            "4.1.6 / CometChatUIKitSwift 5.1.16 (+ WebRTC 124.0.4 + the I7 companion pods); CocoaPods resolves it "
            "cleanly and the kit's in-call UI renders. No post_install/RCTBridge workaround and no custom-view "
            "startSession(callToken:callSetting:view:) bypass is required. The commonly-stated blocker \"4.2.3 is "
            "the newest CallsSDK compatible with the CometChatSDK 4.1.x line\" is FALSE. IMPORTANT — do not ship the "
            "wrong reason: 5.0.1 STILL embeds React Native (RCTBridge present, ~2376 RN symbols), so \"5.x removed "
            "RN\" is untrue; the fix is strictly EMPIRICAL (the 5.0.1 RN build does not trip the PAC/unwinder fault "
            "on iOS 26, 4.2.3 does — which also rules out \"iOS 26 PAC\" as a general cause, since a newer 26.5 sim "
            "renders fine on 5.0.1). CometChat should fix the 4.2.3 crash or document that the 5.0.x Calls line is "
            "REQUIRED for iOS 26, even against the 4.1.x chat SDK. Affects every native-iOS use case. Watch-outs "
            "after the bump: (a) only the FIRST call per launch connects — subsequent calls never transition to the "
            "ongoing screen (kit state bug); (b) a separate SIGSEGV in CometChatCallBubble.setupStyle (CallType "
            "rawValue on null) when rendering a group-call history bubble."},
    {"id": "expo-android-splash-color", "phase": "pre", "families": {"rn"},
     "sig": r"resource color/splashscreen_background not found|splashscreen_background", "fix": _fix_expo_android_splash,
     "note": "RN/Expo prebuild references @color/splashscreen_background in splashscreen.xml but omits it from "
             "colors.xml → release assembleRelease resource-linking fails; define the color (codegen gap).",
     "owner": "harness"},
    {"id": "disk-full", "phase": "on_fail", "families": None,
     "sig": r"ENOSPC|No space left|disk full|write error", "fix": _fix_disk,
     "note": "UC1: builds filled the disk and crashed Docker", "owner": "harness"},
    {"id": "android-sdk", "phase": "on_fail", "families": {"rn", "flutter", "android-native"},
     "sig": r"SDK location not found|ANDROID_HOME|Define a valid SDK location|sdk\.dir", "fix": _fix_android_sdk,
     "note": "android gradle build needs sdk.dir/ANDROID_HOME (codegen omits machine-specific local.properties)",
     "owner": "harness"},
    {"id": "web-cometchat-creds", "phase": "pre", "families": {"web"}, "when_integrated": True,
     "sig": r"Missing VITE_COMETCHAT|Missing .*COMETCHAT_APP_ID|COMETCHAT_APP_ID.*(null|empty|undefined)",
     "fix": _fix_web_cometchat_creds, "owner": "harness", "witness": False,
     "note": "web BUILD-time CometChat creds (VITE_/NEXT_PUBLIC_/REACT_APP_ *_COMETCHAT_APP_ID) left empty by "
             "codegen — provision writes .env.cometchat + compose-env feeds the backend, but the web .env "
             "placeholder is never filled, so the SDK init throws and no chat/call works. Fill from provisioned env."},
    {"id": "compose-env", "phase": "pre", "families": None, "when_integrated": True,
     "sig": None, "fix": _fix_compose_env,
     "note": "UC1: inject COMETCHAT_* into the deployment env, not just .env.example", "owner": "skills",
     "gap": "The production/deployment skill must document injecting COMETCHAT_* into the RUNTIME deployment env "
            "(docker-compose/service), not just .env.example — otherwise the backend mints an EMPTY auth token and "
            "the conversation list errors ('Oops') on every client."},
    {"id": "cometchat-creds", "phase": "pre", "families": {"rn", "flutter"}, "when_integrated": True,
     "sig": r"your_app_id_here|apiclient-[a-z0-9]*\.cometchat|APP ?ID.*(null|invalid)", "fix": _fix_cometchat_creds,
     "note": "UC1 F-mobile-creds: bake real appId or the socket dials a dead host", "owner": "sdk",
     "witness": False,  # proactive cred injection — does NOT prove the placeholder-dead-host behavior was hit
     "gap": "The SDK/skill should FAIL LOUDLY on a placeholder/invalid appId instead of silently dialing a dead host "
            "(apiclient-<appId>.cometchat.io); the native recipe must write the REAL appId to .env, not leave the "
            ".env.example placeholder."},
]


def _match(rule, ctx, err: str | None) -> bool:
    fam = ctx.get("family")
    if rule["families"] is not None and fam not in rule["families"]:
        return False
    if rule.get("when_integrated") and not ctx.get("integrated"):
        return False
    if rule["phase"] == "pre":
        return True
    return bool(rule.get("sig") and err and re.search(rule["sig"], err, re.IGNORECASE))


def _finding_dirs():
    ps = Path(__file__).resolve().parents[2] / "pipeline-state"
    return ps / "gaps", ps / "pipeline-notes"


def _record_finding(ctx: dict, rule: dict, detail: str, evidence: str) -> None:
    """WITNESS: a fired self-heal rule means skill-guided code hit a wall that needed a workaround — the
    definition of a skill/SDK/docs gap. Record it so self-heal can't fix-and-hide. skills/docs/sdk owners
    → the gaps ledger the user reads; harness/setup → pipeline-notes. Idempotent per (slug, rule)."""
    if rule.get("witness") is False:   # proactive guard that doesn't prove the failure was actually hit
        return
    slug = ctx.get("slug") or (Path(ctx["repo_dir"]).name if ctx.get("repo_dir") else None)
    if not slug:
        return
    owner = rule.get("owner", "harness")
    to_ledger = owner in ("skills", "docs", "sdk")
    gaps_dir, notes_dir = _finding_dirs()
    d = gaps_dir if to_ledger else notes_dir
    try:
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{slug}.md"
        marker = f"<!-- selfheal:{rule['id']} -->"
        body = f.read_text() if f.exists() else ""
        if marker in body:
            return
        tag = {"skills": "missedTrigger:", "docs": "coverageGap:", "sdk": "SDK-gap:"}.get(owner, "note:")
        ev = re.sub(r"\s+", " ", (evidence or "")).strip()[:200]
        entry = (f"{marker}\n- **`{tag}`** [self-heal:{rule['id']}] {rule.get('gap') or rule.get('note')}\n"
                 f"  - _auto-repaired by the harness (fix's existence IS the finding)_: {detail}\n"
                 + (f"  - _trigger evidence_: `{ev}`\n" if ev else ""))
        if not body.strip():
            title = "CometChat skills/SDK/docs inconsistencies" if to_ledger else "harness/setup notes"
            body = f"# {slug} — {title} (self-heal witnessed)\n"
        hdr = "## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)"
        if hdr not in body:
            body = body.rstrip() + "\n\n" + hdr + "\n"
        f.write_text(body.rstrip() + "\n" + entry + "\n")
    except Exception:
        pass  # never let finding-recording break a build


def preapply(ctx: dict) -> list[dict]:
    """Run all proactive guards for this component. Returns the applied fixes AND records each as a
    skills/SDK/docs (or harness) finding — self-heal witnesses the gap it repairs."""
    ctx.setdefault("family", stack_family(ctx.get("stack", "")))
    applied = []
    for r in RULES:
        if r["phase"] == "pre" and _match(r, ctx, None):
            ok, detail = r["fix"](ctx)
            if ok:
                applied.append({"rule": r["id"], "detail": detail, "note": r["note"], "owner": r.get("owner")})
            # Record the finding when the guard applied a change (ok) OR when it reports the workaround
            # is ALREADY present ("already ..."). A proactive guard whose workaround is already
            # satisfied — by codegen, a prior run, or a manual edit — must STILL document its recurring
            # gap: the gap (an SDK crash, a skill omission) is inherent to the stack, not to whether we
            # had to repair it this run. Gating recording on `ok` alone made self-heal silently "forget"
            # any recurring gap it didn't actively fix this pass. "not applicable" details ("no app dir",
            # "does not use calls", "not an android project") are correctly skipped.
            if ok or "already" in str(detail).lower():
                _record_finding(ctx, r, detail, "proactive guard — workaround present for this stack")
    return applied


def heal(ctx: dict, error_text: str) -> list[dict]:
    """Match the failure against reactive rules, apply fixes, and record each as a finding (with the
    triggering error as evidence). Returns applied fixes (caller retries)."""
    ctx.setdefault("family", stack_family(ctx.get("stack", "")))
    applied = []
    for r in RULES:
        if r["phase"] == "on_fail" and _match(r, ctx, error_text):
            ok, detail = r["fix"](ctx)
            applied.append({"rule": r["id"], "applied": ok, "detail": detail, "note": r["note"], "owner": r.get("owner")})
            if ok:
                m = re.search(r["sig"], error_text or "", re.IGNORECASE) if r.get("sig") else None
                _record_finding(ctx, r, detail, m.group(0) if m else (error_text or "")[:200])
    return [a for a in applied if a["applied"]]
