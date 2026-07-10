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
    """UC1: gradle needs JDK 17 (JDK 26 → 'Unsupported class file major version 70'). Pin JAVA_HOME."""
    from lib import mobile
    if os.path.isdir(mobile.JDK17):
        ctx.setdefault("env", {})["JAVA_HOME"] = mobile.JDK17
        return True, f"JAVA_HOME={mobile.JDK17}"
    return False, "JDK17 not installed"


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


def _fix_disk(ctx) -> tuple[bool, str]:
    """Reclaim disk (UC1 filled it and crashed Docker). Prune build transients."""
    from lib import mobile
    mobile.cleanup_build_artifacts(Path(ctx["mobile_dir"]) if ctx.get("mobile_dir") else None)
    return True, f"pruned transients; free={mobile.disk_free_gb()}GB"


def _fix_compose_env(ctx) -> tuple[bool, str]:
    """UC1: integrate wired COMETCHAT_* into code but not docker-compose → SDK init fails at boot.
    (Handled today by the integrate prompt + manual wiring; recorded as a guard so it's checked.)"""
    return False, "compose-env is a codegen-guard (integrate prompt); no runtime patch"


# ---------- rule registry ----------
# phase: 'pre' = proactive before build · 'on_fail' = reactive on a matching failure
RULES = [
    {"id": "cometchat-creds", "phase": "pre", "families": {"rn", "flutter"}, "when_integrated": True,
     "sig": r"your_app_id_here|apiclient-[a-z0-9]*\.cometchat|APP ?ID.*(null|invalid)", "fix": _fix_cometchat_creds,
     "note": "UC1 F-mobile-creds: bake real appId or the socket dials a dead host"},
    {"id": "cleartext-http", "phase": "pre", "families": {"rn", "flutter"},
     "sig": r"CLEARTEXT|ERR_CLEARTEXT|App Transport Security|NSAllowsArbitraryLoads", "fix": _fix_cleartext,
     "note": "UC1: release builds block cleartext to the local HTTP backend"},
    {"id": "jdk17", "phase": "on_fail", "families": {"rn", "flutter", "android-native"},
     "sig": r"Unsupported class file major version|invalid source release|requires Java", "fix": _fix_jdk17,
     "note": "UC1: gradle needs JDK 17"},
    {"id": "gradle-stale", "phase": "on_fail", "families": {"rn", "flutter", "android-native"},
     "sig": r"Could not read workspace metadata|metadata\.bin|corrupt", "fix": _fix_gradle_stale,
     "note": "UC1: stop stale gradle daemon after a cache wipe"},
    {"id": "pod-modular", "phase": "on_fail", "families": {"rn", "flutter", "ios-native"},
     "sig": r"does not define modules|SPTPersistentCache|DVAssetLoaderDelegate|use_modular_headers", "fix": _fix_pod_modular,
     "note": "UC1: Swift CometChat pod needs modular headers"},
    {"id": "disk-full", "phase": "on_fail", "families": None,
     "sig": r"ENOSPC|No space left|disk full|write error", "fix": _fix_disk,
     "note": "UC1: builds filled the disk and crashed Docker"},
    {"id": "compose-env", "phase": "pre", "families": None, "when_integrated": True,
     "sig": None, "fix": _fix_compose_env,
     "note": "UC1: inject COMETCHAT_* into the deployment env, not just .env.example"},
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


def preapply(ctx: dict) -> list[dict]:
    """Run all proactive guards for this component. Returns the applied fixes."""
    ctx.setdefault("family", stack_family(ctx.get("stack", "")))
    applied = []
    for r in RULES:
        if r["phase"] == "pre" and _match(r, ctx, None):
            ok, detail = r["fix"](ctx)
            if ok:
                applied.append({"rule": r["id"], "detail": detail, "note": r["note"]})
    return applied


def heal(ctx: dict, error_text: str) -> list[dict]:
    """Match the failure against reactive rules, apply fixes. Returns applied fixes (caller retries)."""
    ctx.setdefault("family", stack_family(ctx.get("stack", "")))
    applied = []
    for r in RULES:
        if r["phase"] == "on_fail" and _match(r, ctx, error_text):
            ok, detail = r["fix"](ctx)
            applied.append({"rule": r["id"], "applied": ok, "detail": detail, "note": r["note"]})
    return [a for a in applied if a["applied"]]
