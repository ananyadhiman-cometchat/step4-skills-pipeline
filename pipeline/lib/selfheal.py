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


# ---------- rule registry ----------
# phase: 'pre' = proactive before build · 'on_fail' = reactive on a matching failure
RULES = [
    {"id": "cleartext-http", "phase": "pre", "families": {"rn", "flutter"},
     "sig": r"CLEARTEXT|ERR_CLEARTEXT|App Transport Security|NSAllowsArbitraryLoads", "fix": _fix_cleartext,
     "note": "UC1: release builds block cleartext to the local HTTP backend",
     "owner": "skills",
     "gap": "The mobile native-setup skill must document that a RELEASE build talking to a local HTTP backend "
            "needs android:usesCleartextTraffic + a network_security_config AND the INTERNET permission in the "
            "MAIN manifest (Flutter injects INTERNET only into the DEBUG manifest) + iOS ATS NSAllowsArbitraryLoads."},
    {"id": "jdk17", "phase": "on_fail", "families": {"rn", "flutter", "android-native"},
     "sig": r"Unsupported class file major version|invalid source release|requires Java", "fix": _fix_jdk17,
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
    {"id": "disk-full", "phase": "on_fail", "families": None,
     "sig": r"ENOSPC|No space left|disk full|write error", "fix": _fix_disk,
     "note": "UC1: builds filled the disk and crashed Docker", "owner": "harness"},
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
                _record_finding(ctx, r, detail, "proactive guard — pre-empts the known failure signature")
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
