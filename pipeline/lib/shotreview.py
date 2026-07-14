"""shotreview — Claude-vision rubric judging over a set of shots + a self-contained HTML gallery.

  vision.judge  → "is it correct?"  (Claude-vision rubric pass/fail per check)

(The perceptual-baseline "did it change?" layer was removed: on live fake-media call frames it
flagged CHANGED every run, fed no gate, and only trained reviewers to ignore the ⚠.)

Produces a single self-contained HTML gallery (images inlined as base64) so CP1/CP2 review is one
page, plus a compact machine summary the verify/demo stages fold into their verdict.
"""
from __future__ import annotations
import base64, html, json
from pathlib import Path
from lib import vision


def _b64(p: Path) -> str:
    try:
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
    except Exception:
        return ""


def _card(item: dict) -> str:
    v, bl = item.get("vision", {}), item.get("baseline", {})
    vpass = v.get("overallPass"); status = bl.get("status", "n/a")
    badge = "#16a34a" if vpass else "#dc2626"
    checks = "".join(
        f'<li style="color:{"#16a34a" if c.get("pass") else "#dc2626"}">'
        f'[{"PASS" if c.get("pass") else "FAIL"}] <b>{html.escape(str(c.get("id")))}</b>: '
        f'{html.escape(str(c.get("reason",""))[:200])}</li>'
        for c in v.get("checks", []))
    img = _b64(Path(item["path"])) if Path(item["path"]).exists() else ""
    return (
        f'<div style="border:1px solid #ddd;border-radius:10px;margin:14px 0;padding:14px;font-family:system-ui">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<h3 style="margin:0">{html.escape(item["name"])} '
        f'<span style="font-size:12px;color:#666">({html.escape(item.get("context",""))})</span></h3>'
        f'<span style="background:{badge};color:#fff;padding:3px 10px;border-radius:12px;font-size:12px">'
        f'{"CORRECT" if vpass else "FAILED"}</span></div>'
        f'<div style="display:flex;gap:16px;margin-top:10px;flex-wrap:wrap">'
        f'<img src="{img}" style="max-width:520px;width:100%;border:1px solid #eee;border-radius:6px"/>'
        f'<div style="flex:1;min-width:280px">'
        f'<div style="font-size:13px;color:#333;margin-bottom:6px">rubric: <b>{html.escape(v.get("rubric","-"))}</b></div>'
        f'<ul style="font-size:13px;line-height:1.5;padding-left:18px;margin:0">{checks or "<li>no checks</li>"}</ul>'
        f'<div style="margin-top:8px;font-size:13px">baseline: <b>{html.escape(status)}</b>'
        + (f' · score={bl.get("score")} · dhashΔ={bl.get("hammingDist")}' if "score" in bl else "")
        + (f'<br><i style="color:#b45309">{html.escape(bl["note"])}</i>' if bl.get("note") else "")
        + '</div></div></div></div>')


def review(shots: list[dict], slug: str, settings: dict, out_html: str,
           baselines_dir: str = "~/Desktop/automate/pipeline-state/baselines",
           baseline_backend: str = "local") -> dict:
    """shots: [{name, path, rubric, context}]. Runs vision + baseline on each, writes the gallery
    to out_html, returns {allCorrect, anyChanged, results, gallery}."""
    results = []
    for s in shots:
        v = vision.judge(s["path"], s.get("rubric", "app_alive"), s.get("context", s["name"]), settings) \
            if Path(s["path"]).exists() else {"ok": False, "overallPass": False, "error": "missing shot", "checks": []}
        results.append({**s, "vision": v, "baseline": {}})
    allCorrect = all(r["vision"].get("overallPass") for r in results) if results else False
    anyChanged = False   # perceptual baseline removed: flaky on live fake-media call frames, gated nothing
    body = "".join(_card(r) for r in results)
    Path(out_html).parent.mkdir(parents=True, exist_ok=True)
    Path(out_html).write_text(
        f'<html><head><meta charset="utf-8"><title>Shot review — {html.escape(slug)}</title></head>'
        f'<body style="max-width:1100px;margin:20px auto;font-family:system-ui">'
        f'<h1>Screenshot review — {html.escape(slug)}</h1>'
        f'<p>vision = "is it correct?" · baseline = "did it change?" · '
        f'<b style="color:{"#16a34a" if allCorrect else "#dc2626"}">'
        f'{"ALL CORRECT" if allCorrect else "ISSUES FOUND"}</b>'
        f'{" · ⚠ VISUAL CHANGES" if anyChanged else ""}</p>{body}</body></html>')
    # compact machine summary (no base64) for state
    summary = [{"name": r["name"], "correct": r["vision"].get("overallPass"),
                "baseline": r["baseline"].get("status"),
                "failedChecks": [c["id"] for c in r["vision"].get("checks", []) if not c.get("pass")]}
               for r in results]
    return {"allCorrect": allCorrect, "anyChanged": anyChanged, "gallery": out_html, "results": summary}
