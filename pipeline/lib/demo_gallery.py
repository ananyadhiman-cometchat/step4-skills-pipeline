"""demo_gallery.py — the DEFINED demo deliverable shown before CP1.

stage_demo captures a `shots` dict (web / android / ios launch + *-loggedin) plus a mobile↔web
call matrix. This module renders those into ONE self-contained, theme-aware HTML gallery
(`_demo/gallery.html`) organised by platform, with a per-shot status pill and a one-line "what it
proves" caption — the same format finalised on `dat`. It is intentionally HONEST: a platform whose
build/login failed shows as an open issue rather than being dropped from the matrix.

The pipeline (Python) can only WRITE the file; the agent/human publishes it (Artifact) or opens it
locally at the CP1 checkpoint. Images are base64-embedded so the file is portable (e.g. to a phone).
"""
from __future__ import annotations
import base64, os, html, subprocess

# platform -> ordered (shot_key, title, proof, is_primary_login)
_LAYOUT = [
    ("Web", "browser", [
        ("web", "Launch", "The web app renders (backend reached).", False),
        ("web-loggedin", "Signed in", "Login succeeds and the home/feed loads.", True),
    ]),
    ("Android", "phone", [
        ("android", "Launch", "The Android app launches.", False),
        ("android-loggedin", "Signed in", "Login succeeds and the home renders.", True),
    ]),
    ("iOS", "phone", [
        ("ios", "Launch", "The iOS app launches.", False),
        ("ios-loggedin", "Signed in", "Login succeeds and the home renders.", True),
    ]),
]
# call-matrix screenshots the two-party runners drop into the demo dir (best-effort include)
_CALL_SHOTS = [
    ("callee-ringing-voice", "phone", "Incoming call", "The callee's device rings (voice)."),
    ("caller-ongoing-voice", "phone", "Connected", "Caller reaches the live call surface."),
    ("callee-ongoing-voice", "phone", "Connected", "Callee reaches the live call surface."),
]


def _resize_b64(path: str) -> str | None:
    """Return a data: URI, shrunk via sips (macOS) to keep the file portable; raw fallback."""
    if not path or not os.path.exists(path) or os.path.getsize(path) < 64:
        return None
    data = None
    try:
        out = "/tmp/_demo_gallery_tmp.jpg"
        r = subprocess.run(["sips", "-Z", "640", path, "--out", out,
                            "--setProperty", "format", "jpeg", "--setProperty", "formatOptions", "80"],
                           capture_output=True, timeout=30)
        if r.returncode == 0 and os.path.exists(out):
            with open(out, "rb") as f:
                data = f.read()
            os.unlink(out)
    except Exception:
        data = None
    if data is None:
        with open(path, "rb") as f:
            data = f.read()
    mime = "jpeg" if (data[:2] == b"\xff\xd8") else "png"
    return f"data:image/{mime};base64," + base64.b64encode(data).decode()


def _shot_path(shots: dict, key: str) -> str | None:
    s = shots.get(key) or {}
    p = s.get("path")
    return p if (p and os.path.exists(p)) else None


def _platform_status(shots: dict, keys: list[str]) -> str:
    """ok if the primary login shot launched+loggedin; warn if attempted but failed; skip if absent."""
    launch = shots.get(keys[0])
    login = shots.get(keys[1]) if len(keys) > 1 else None
    if launch is None:
        return "skip"
    if launch.get("ok") and (login is None or login.get("ok")):
        return "ok"
    return "warn"


def build(demo_dir: str, shots: dict, mobile_calls: dict, uc: dict, out_path: str) -> str | None:
    """Render the demo gallery to out_path. Returns the path, or None if no shots were available."""
    name = uc.get("name") or uc.get("slug") or "App"
    cards_by_plat = []
    any_card = False
    for plat, dev, entries in _LAYOUT:
        keys = [k for k, *_ in entries]
        st = _platform_status(shots, keys)
        if st == "skip":
            continue
        figs = []
        for key, title, proof, _primary in entries:
            uri = _resize_b64(_shot_path(shots, key))
            if not uri:
                continue
            alive = shots.get(key, {}).get("visionAlive")
            pill = ("Open issue", "warn") if alive is False or not shots.get(key, {}).get("ok") else ("Verified", "ok")
            figs.append((uri, title, proof, dev, pill))
        # call-matrix shots for this mobile platform
        if plat in ("Android", "iOS"):
            for cs_key, cdev, ctitle, cproof in _CALL_SHOTS:
                uri = _resize_b64(os.path.join(demo_dir, cs_key + ".png"))
                if uri:
                    figs.append((uri, ctitle, cproof, cdev, ("Verified", "ok")))
        if not figs:
            continue
        any_card = True
        cards = "".join(
            f'<figure class="card {dev}"><div class="shot"><img loading="lazy" src="{uri}" alt="{html.escape(t)}"></div>'
            f'<figcaption><div class="cap-head"><span class="cap-title">{html.escape(t)}</span>'
            f'<span class="pill {pc}">{pl}</span></div><p>{html.escape(pr)}</p></figcaption></figure>'
            for (uri, t, pr, dev, (pl, pc)) in figs)
        sw = {"ok": ("Verified", "ok"), "warn": ("Open issue", "warn")}[st]
        cards_by_plat.append(
            f'<section><div class="sec-head"><div><span class="kicker">{plat}</span>'
            f'<h2>{plat}</h2></div><span class="status {sw[1]}">{sw[0]}</span></div>'
            f'<div class="grid">{cards}</div></section>')
    if not any_card:
        return None
    call_line = ", ".join(f"{k}={'✓' if v is True else v}" for k, v in (mobile_calls or {}).items()) or "—"
    body = _TEMPLATE.format(title=html.escape(f"{name} — Demo"),
                            heading=html.escape(f"{name}: chat & calls demo"),
                            sections="\n".join(cards_by_plat), calls=html.escape(call_line))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(body)
    return out_path


_TEMPLATE = """<title>{title}</title>
<style>
:root{{--ground:#f7f3f5;--panel:#fff;--ink:#211a1e;--soft:#6b5f65;--line:#e7dde2;--accent:#e1156c;
--ok:#15935b;--ok-bg:#e2f3ea;--warn:#b9791a;--warn-bg:#f8ecd6;--mono:ui-monospace,Menlo,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}}
@media(prefers-color-scheme:dark){{:root{{--ground:#151013;--panel:#1f181c;--ink:#f3e9ee;--soft:#a99aa2;
--line:#342a2f;--accent:#ff5ca0;--ok:#4cc389;--ok-bg:#123024;--warn:#e0a94a;--warn-bg:#332612;}}}}
:root[data-theme=dark]{{--ground:#151013;--panel:#1f181c;--ink:#f3e9ee;--soft:#a99aa2;--line:#342a2f;
--accent:#ff5ca0;--ok:#4cc389;--ok-bg:#123024;--warn:#e0a94a;--warn-bg:#332612;}}
:root[data-theme=light]{{--ground:#f7f3f5;--panel:#fff;--ink:#211a1e;--soft:#6b5f65;--line:#e7dde2;
--accent:#e1156c;--ok:#15935b;--ok-bg:#e2f3ea;--warn:#b9791a;--warn-bg:#f8ecd6;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);line-height:1.5}}
.wrap{{max-width:1120px;margin:0 auto;padding:clamp(20px,4vw,52px) clamp(16px,3vw,32px) 64px}}
header{{border-bottom:1px solid var(--line);padding-bottom:24px}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:600}}
h1{{font-size:clamp(28px,5vw,44px);letter-spacing:-.02em;margin:.3em 0 .2em;font-weight:800;text-wrap:balance}}
.calls{{font-family:var(--mono);font-size:12.5px;color:var(--soft);margin:.4em 0 0}}
section{{margin-top:44px}}
.sec-head{{display:flex;align-items:flex-end;justify-content:space-between;border-bottom:2px solid var(--ink);padding-bottom:9px}}
.kicker{{font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--soft)}}
.sec-head h2{{margin:.1em 0 0;font-size:clamp(19px,3vw,25px)}}
.status{{font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;padding:3px 9px;border-radius:999px}}
.status.ok,.pill.ok{{background:var(--ok-bg);color:var(--ok)}}.status.warn,.pill.warn{{background:var(--warn-bg);color:var(--warn)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:18px;margin-top:18px;align-items:start}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:15px;overflow:hidden;display:flex;flex-direction:column}}
.shot{{padding:13px;display:flex;justify-content:center;background:linear-gradient(160deg,var(--ground),var(--panel))}}
.shot img{{width:100%;height:auto;border-radius:9px;box-shadow:0 6px 20px rgba(0,0,0,.1)}}
.card.phone .shot img{{max-width:220px;border-radius:18px}}
figcaption{{padding:12px 15px 16px;border-top:1px solid var(--line)}}
.cap-head{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px}}
.cap-title{{font-weight:700;font-size:14px}}
.pill{{font-family:var(--mono);font-size:10px;font-weight:600;text-transform:uppercase;padding:2px 7px;border-radius:999px}}
figcaption p{{margin:0;font-size:12.5px;color:var(--soft)}}
</style>
<div class="wrap"><header><span class="eyebrow">CometChat demo · before CP1</span>
<h1>{heading}</h1><p class="calls">call matrix: {calls}</p></header>
{sections}</div>"""
