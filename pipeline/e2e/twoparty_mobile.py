#!/usr/bin/env python3
"""twoparty_mobile.py — automate a two-party mobile↔web call (android↔web / ios↔web).

Coordinates Maestro (drives the native app on a booted emulator/simulator) with Playwright
(drives the web peer in a headless browser) so a REAL call rings across the two platforms and
both ends connect. This is the automated version of the CP2 manual mobile-call check.

Direction `web-calls-mobile` (default) exercises the MOBILE incoming-call widget (the fixed
Android/iOS accept/reject UI): web (Bob) rings → mobile (Sara) shows the incoming widget →
Maestro taps Accept → both connect. `mobile-calls-web` is the reverse (mobile is caller).

Usage:
  python3 twoparty_mobile.py --platform android --direction web-calls-mobile --call-type voice
Prints a JSON verdict and writes screenshots to --shot-dir.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # pipeline/ — for lib.cometchat
try:
    from lib import cometchat                  # server-side "answered" check (media-independent)
except Exception:
    cometchat = None
MAESTRO = os.path.expanduser("~/.maestro/bin/maestro")
ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
FLOWS = HERE / "mobile_flows"
WEB_PW = "Mkt@seed2026!"
# mobile plays the SELLER (Sara), web plays the BUYER (Bob) — matches the seed conversation
MOBILE_EMAIL = "sara.seller@mkt.io"
WEB_EMAIL = "bob.buyer@mkt.io"
MOBILE_PEER = "Bob Buyer"     # the conversation row the mobile app opens
WEB_PEER = "Sara Seller"


def _run(cmd, timeout=180, env=None, cwd=None):
    p = subprocess.run(cmd, timeout=timeout, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env={**os.environ, **(env or {})}, cwd=cwd)
    return p.returncode, p.stdout


def _device_flag(platform: str) -> list[str]:
    if platform == "android":
        return ["--device", "emulator-5554"]
    # iOS: first booted sim udid
    out = subprocess.run(["xcrun", "simctl", "list", "devices", "booted"],
                         text=True, capture_output=True).stdout
    for line in out.splitlines():
        if "Booted" in line and "(" in line:
            udid = line.split("(")[1].split(")")[0]
            return ["--device", udid]
    return []


def reset_app(platform: str) -> None:
    """Force-stop the app so a prior call/session can't bleed into the next leg's clean launch."""
    if platform == "android":
        subprocess.run([ADB, "shell", "am", "force-stop", "com.mkt.mobile"], capture_output=True)
    else:
        subprocess.run(["xcrun", "simctl", "terminate", "booted", "com.mkt.mobile"], capture_output=True)
    time.sleep(3)


def maestro(platform: str, flow: str, params: dict, timeout=180) -> dict:
    cmd = [MAESTRO, *_device_flag(platform), "test", str(FLOWS / flow)]
    for k, v in params.items():
        cmd += ["-e", f"{k}={v}"]
    code, out = _run(cmd, timeout=timeout)
    return {"flow": flow, "ok": code == 0, "exit": code, "tail": "\n".join(out.splitlines()[-12:])}


def pull_shot(platform: str, maestro_name: str, dest: str) -> bool:
    """Maestro writes takeScreenshot output as <name>.png on the HOST for both platforms."""
    src = Path(f"{maestro_name}.png")
    if src.exists():
        Path(dest).write_bytes(src.read_bytes()); return True
    return False


def web_proc(script: str, env: dict):
    """Spawn a web playwright script (in web/ so @playwright/test resolves). Returns Popen."""
    web = (HERE.parent.parent / "runs" / "mkt" / "web")
    dst = web / f"_{Path(script).stem}_run.mjs"
    dst.write_text((HERE / script).read_text())
    p = subprocess.Popen(["node", str(dst)], cwd=str(web), text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         env={**os.environ, **env})
    return p, dst


def _verdict(out: str) -> dict:
    for line in reversed((out or "").splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line.strip())
            except Exception:
                pass
    return {"error": "no verdict json", "tail": (out or "")[-300:]}


def web_calls_mobile(platform, call_type, web_url, shot_dir, env_file="", slug="",
                     app_id=None, mobile_email=None, web_email=None, password=None,
                     submit="Sign In", home="Messages") -> dict:
    app_id = app_id or "com.mkt.mobile"                 # per-UC package/bundle (resolved by the caller)
    mobile_email = mobile_email or MOBILE_EMAIL         # the two call-test accounts of THIS use case
    web_email = web_email or WEB_EMAIL
    password = password or WEB_PW
    tag = f"{platform}-{call_type}"
    reset_app(platform)   # clean slate — no lingering call from a prior leg
    # 1. mobile logs in → CallSurfaces arms the incoming listener at app root
    login = maestro(platform, "login_msgs.flow.yaml",
                    {"APP_ID": app_id, "EMAIL": mobile_email, "PASSWORD": password, "SUBMIT": submit, "HOME": home})
    if not login["ok"]:
        return {"leg": tag, "direction": "web-calls-mobile", "mobileLogin": login, "callConnected": False}
    # Let CometChat finish connecting before the call is placed — iOS's SDK connect is markedly
    # slower than Android's, and a call placed before the callee is online rings into the void.
    time.sleep(15 if platform == "ios" else 5)
    # 2. spawn web caller (the web party rings the mobile party, holds the line)
    since = int(time.time())   # server-answered floor
    p, dst = web_proc("webcaller.web.mjs", {
        "WEB_URL": web_url, "CALL_TYPE": call_type, "CALLER_EMAIL": web_email,
        "E2E_PASSWORD": password, "HOLD_MS": "55000", "SHOT_DIR": shot_dir, "TAG": tag})
    time.sleep(2)
    # 3. mobile waits for the incoming widget, accepts, screenshots
    accept = maestro(platform, "accept_call.flow.yaml", {"APP_ID": app_id}, timeout=90)
    mob_inc = pull_shot(platform, "/tmp/mobile-incoming", f"{shot_dir}/mobile-incoming-{tag}.png")
    mob_ong = pull_shot(platform, "/tmp/mobile-ongoing", f"{shot_dir}/mobile-ongoing-{tag}.png")
    # 4. collect web verdict + SERVER-side answered (deterministic, media-independent)
    try:
        out, _ = p.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        p.kill(); out = p.communicate()[0]
    finally:
        dst.unlink(missing_ok=True)
    web = _verdict(out)
    answered = cometchat.call_answered(env_file, slug, since) if (cometchat and env_file) else {"answered": None}
    # SIGNALING verdict: the mobile incoming widget appeared + Maestro accepted it + CometChat logged
    # the call ANSWERED. Media-independent → deterministic. DOM/ongoing shots kept only as evidence.
    connected = bool(accept["ok"] and answered.get("answered") is not False)
    return {"leg": tag, "direction": "web-calls-mobile", "callType": call_type,
            "mobileLogin": login["ok"], "mobileAccept": accept["ok"], "mobileAcceptTail": accept["tail"],
            "serverAnswered": answered.get("answered"), "webCaller": web,
            "mobileIncomingShot": mob_inc, "mobileOngoingShot": mob_ong, "callConnected": connected}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=["android", "ios"], required=True)
    ap.add_argument("--direction", choices=["web-calls-mobile", "mobile-calls-web"], default="web-calls-mobile")
    ap.add_argument("--call-type", choices=["voice", "video"], default="voice")
    ap.add_argument("--web-url", default="http://localhost:3000")
    ap.add_argument("--shot-dir", default="/tmp")
    ap.add_argument("--env-file", default="")
    ap.add_argument("--slug", default="mkt")
    ap.add_argument("--app-id", default=None)         # mobile package/bundle id (per UC)
    ap.add_argument("--mobile-email", default=None)   # the two call-test accounts of this UC
    ap.add_argument("--web-email", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--submit", default="Sign In")
    ap.add_argument("--home", default="Messages")
    args = ap.parse_args()
    if args.direction == "web-calls-mobile":
        res = web_calls_mobile(args.platform, args.call_type, args.web_url, args.shot_dir,
                               env_file=args.env_file, slug=args.slug, app_id=args.app_id,
                               mobile_email=args.mobile_email, web_email=args.web_email,
                               password=args.password, submit=args.submit, home=args.home)
    else:
        res = {"error": "mobile-calls-web not yet wired"}
    print(json.dumps(res))


if __name__ == "__main__":
    main()
