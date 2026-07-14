#!/usr/bin/env python3
"""call_matrix_flutter.py — cross-platform Flutter CALL test: android <-> iOS, both directions.

A = jamie (Member) on android · B = marco (Moderator) on iOS. For each direction the CALLER opens the
peer's conversation thread and taps a call button; the CALLEE (on the other device) accepts the incoming
overlay. VERDICT is media-independent: cometchat.call_answered() reads the server-side call message action
(initiated → ongoing → ended) for the callee's uid — so it passes on a simulator/emulator where WebRTC
media won't render but the signaling + accept DO complete. This is exactly the bug surface the user hit:
"accept → rejected" means the call never reached 'ongoing'.

Usage: python3 call_matrix_flutter.py           (both directions)
"""
import os, subprocess, sys, time, tempfile
sys.path.insert(0, os.path.expanduser("~/Desktop/automate/pipeline"))
from lib import cometchat

MAESTRO = os.path.expanduser("~/.maestro/bin/maestro")
ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
ENV = os.path.expanduser("~/Desktop/automate/runs/com/.env.cometchat")
ANDROID_DEV = "emulator-5554"
ANDROID_PKG = "io.com.community_forum"
IOS_PKG = "io.com.communityForum"
SHOT = os.path.expanduser("~/Desktop/automate/runs/com/_demo")
CFG = cometchat._cfg(ENV)
# (role demo-button label, cometchat uid) for each account
JAMIE = ("Member", "com-mem-001")      # android
MARCO = ("Moderator", "com-mod-001")   # iOS


def ios_udid():
    out = subprocess.run(["xcrun", "simctl", "list", "devices", "booted"], text=True, capture_output=True).stdout
    import re
    m = re.search(r"\(([0-9A-F-]{36})\)", out)
    return m.group(1) if m else None


def run_flow(device, steps, name, extra_env=None, timeout=140):
    """Write a Maestro flow (steps = list of yaml lines) and run it on `device`. Returns (ok, out)."""
    pkg = IOS_PKG if "-" in device and len(device) == 36 else ANDROID_PKG
    body = f"appId: {pkg}\n---\n" + "\n".join(steps) + "\n"
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False); f.write(body); f.close()
    env = {**os.environ, "PATH": os.path.expanduser("~/.maestro/bin:") + os.environ.get("PATH", "")}
    p = subprocess.run([MAESTRO, "--device", device, "test", f.name], text=True, capture_output=True, timeout=timeout, env=env)
    os.unlink(f.name)
    ok = p.returncode == 0
    return ok, (p.stdout + p.stderr)


LOGIN_OPEN_THREAD = lambda role: [
    "- launchApp: { clearState: true }",
    f'- tapOn: {{ text: "{role}", optional: true }}',
    "- waitForAnimationToEnd: { timeout: 3000 }",
    '- tapOn: { text: "Sign In", optional: true }',
    '- extendedWaitUntil: { notVisible: { text: "Sign In" }, timeout: 25000 }',
    '- tapOn: { point: "50%,95%" }',                                   # Messages tab
    '- extendedWaitUntil: { visible: { text: "Chats" }, timeout: 40000, optional: true }',
    "- waitForAnimationToEnd: { timeout: 10000 }",                    # let the conversation sync
    '- tapOn: { point: "50%,22%" }',                                 # open the peer's thread
    "- waitForAnimationToEnd: { timeout: 5000 }",
]
LOGIN_HOME = lambda role: [
    "- launchApp: { clearState: true }",
    f'- tapOn: {{ text: "{role}", optional: true }}',
    "- waitForAnimationToEnd: { timeout: 3000 }",
    '- tapOn: { text: "Sign In", optional: true }',
    '- extendedWaitUntil: { notVisible: { text: "Sign In" }, timeout: 25000 }',
    "- waitForAnimationToEnd: { timeout: 4000 }",                     # incoming overlay is global — stay put
]
TAP_CALL = lambda out: [                                              # tap BOTH call-button positions (voice+video)
    '- tapOn: { point: "84%,8%" }',
    "- waitForAnimationToEnd: { timeout: 3500 }",
    f"- takeScreenshot: {out}",
]
ACCEPT = lambda out: [                                                # wait for the incoming overlay, accept it
    '- extendedWaitUntil: { visible: { text: "Accept" }, timeout: 25000, optional: true }',
    '- tapOn: { text: "Accept", optional: true }',
    '- tapOn: { point: "50%,88%" }',                                 # fallback: accept button lower area
    "- waitForAnimationToEnd: { timeout: 6000 }",
    f"- takeScreenshot: {out}",
]


def direction(caller_dev, caller_role, callee_dev, callee_role, callee_uid, label):
    print(f"\n=== {label} ===")
    ok1, _ = run_flow(caller_dev, LOGIN_OPEN_THREAD(caller_role), "caller-login")
    ok2, _ = run_flow(callee_dev, LOGIN_HOME(callee_role), "callee-login")
    print(f"  logins: caller={ok1} callee={ok2}")
    since = int(time.time())
    # caller initiates, then callee accepts (run sequentially — ring persists ~30s)
    run_flow(caller_dev, TAP_CALL(f"{SHOT}/call-{label}-caller"), "tap-call", timeout=60)
    run_flow(callee_dev, ACCEPT(f"{SHOT}/call-{label}-callee"), "accept", timeout=60)
    time.sleep(4)
    v = cometchat.call_answered(ENV, "com", since, poll_s=20, uid=callee_uid)
    print(f"  call_answered(server-side): answered={v.get('answered')} action={v.get('action')}")
    return bool(v.get("answered"))


def main():
    ios = ios_udid()
    if not ios:
        print("no booted iOS simulator"); sys.exit(2)
    if subprocess.run([ADB, "devices"], text=True, capture_output=True).stdout.count("\tdevice") < 1:
        print("no android emulator"); sys.exit(2)
    r1 = direction(ANDROID_DEV, JAMIE[0], ios, MARCO[0], MARCO[1], "android-to-ios")
    r2 = direction(ios, MARCO[0], ANDROID_DEV, JAMIE[0], JAMIE[1], "ios-to-android")
    print(f"\n==== RESULT ====\n  android→ios connected: {r1}\n  ios→android connected: {r2}")
    sys.exit(0 if (r1 and r2) else 1)


if __name__ == "__main__":
    main()
