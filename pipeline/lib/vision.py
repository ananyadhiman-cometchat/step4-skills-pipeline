"""vision — Claude-vision screenshot JUDGE ("is it correct?").

The DOM-selector assertions in this pipeline broke repeatedly (`.cometchat-ongoing-call` vs the
caller's variant, iOS tab labels absent from the a11y tree, accept-button selectors) and the
subtle visual bugs (bottom-left ring, chat bleeding under the call, app header over the call) were
only ever caught by a human eyeballing the screenshot. This module automates that judgment: it
feeds a screenshot + a rubric to Claude (vision) and gets back a structured pass/fail per check.

Answers "is it correct?" against a named rubric (the perceptual "did it change?" baseline was removed).

Reuses the pipeline's `claude -p` auth (no API key needed) — Claude Code reads the image via its
Read tool and returns a strict JSON verdict.
"""
from __future__ import annotations
import json, os, re, subprocess
from pathlib import Path

# Named rubrics — each a list of {id, check} the judge evaluates independently.
# Add per-surface rubrics here; they read like the manual review a human would do.
RUBRICS: dict[str, list[dict]] = {
    "incoming_ring": [
        {"id": "not_corner_toast", "check": "An incoming-call card is visible, positioned as a CENTERED modal, a TOP banner, or a full-screen overlay. It must NOT be tucked into a screen CORNER as a small notification toast (the known bug is a card pinned to the BOTTOM-LEFT corner). A small centered modal card is FINE; only a corner-pinned toast fails."},
        {"id": "accept_reject", "check": "The incoming call shows clearly labelled Accept AND Decline/Reject actions."},
        {"id": "caller_shown", "check": "The caller's name or avatar is visible on the incoming-call card."},
    ],
    "ongoing_call": [
        {"id": "fullscreen", "check": "The ongoing/connected call fills essentially the WHOLE viewport."},
        {"id": "no_app_chrome", "check": "The app's own navigation header/top-bar is NOT visible above the call."},
        {"id": "no_chat_bleed", "check": "No chat conversation / message bubbles / call-log chips are visible behind or below the call controls."},
        {"id": "controls", "check": "Call controls (mute, end-call, etc.) are visible."},
    ],
    "chat_thread": [
        {"id": "list_scrolls", "check": "A message thread is visible and appears to be a scrollable list (messages fill the area, not clipped to a tiny box)."},
        {"id": "composer", "check": "A message composer/input is visible at the bottom."},
    ],
    "feed_loaded": [
        {"id": "has_content", "check": "The screen shows actual loaded content (e.g. listings/items), NOT an empty state, a spinner, or 'no results'."},
        {"id": "no_error", "check": "No error/crash/blank-white screen is shown."},
    ],
    "app_alive": [
        {"id": "rendered", "check": "The app has rendered real UI (not a blank/white screen, not a red error box, not just a loading spinner)."},
    ],
}


def _vision_model(settings: dict | None) -> str:
    if settings:
        return settings.get("models", {}).get("vision") or settings.get("models", {}).get("build", "claude-sonnet-4-6")
    return "claude-sonnet-4-6"


def _claude_bin(settings: dict | None) -> str:
    return (settings or {}).get("claude_bin", "claude")


def judge_screenshot(shot_path: str, checks: list[dict], context: str = "",
                     settings: dict | None = None, timeout: int = 150) -> dict:
    """Grade one screenshot against `checks`. Returns
    {ok, overallPass, checks:[{id, pass, reason}], model, error?}. Never raises."""
    shot = Path(shot_path)
    if not shot.exists() or shot.stat().st_size < 1000:
        return {"ok": False, "overallPass": False, "error": f"missing/empty screenshot: {shot_path}", "checks": []}
    checklist = "\n".join(f'- id="{c["id"]}": {c["check"]}' for c in checks)
    prompt = (
        f"Read the image file at {shot.resolve()} and evaluate it as a QA reviewer.\n"
        f"Context: {context or 'app screenshot from an automated test'}.\n\n"
        f"Evaluate EACH check independently against what is ACTUALLY visible in the image:\n{checklist}\n\n"
        "A check PASSES only if the image clearly satisfies it. If unsure or not visible, FAIL it.\n"
        'Output ONLY a single JSON object, no prose:\n'
        '{"checks":[{"id":"<id>","pass":true|false,"reason":"<short, concrete, references what you saw>"}]}'
    )
    argv = [_claude_bin(settings), "-p", "--model", _vision_model(settings),
            "--max-turns", "6", "--permission-mode", "bypassPermissions",
            "--add-dir", str(shot.parent), "--output-format", "json"]
    try:
        p = subprocess.run(argv, input=prompt, text=True, capture_output=True, timeout=timeout)
        raw = p.stdout or ""
    except subprocess.TimeoutExpired:
        return {"ok": False, "overallPass": False, "error": "vision judge timeout", "checks": []}
    # claude -p --output-format json → envelope with a .result string holding the model's text
    result_text = raw
    try:
        env = json.loads(raw)
        result_text = env.get("result", raw) if isinstance(env, dict) else raw
    except Exception:
        pass
    m = re.search(r'\{.*"checks".*\}', result_text, re.DOTALL)
    if not m:
        return {"ok": False, "overallPass": False, "error": "no JSON verdict from judge",
                "raw": result_text[-300:], "checks": []}
    try:
        verdict = json.loads(m.group(0))
    except Exception as e:
        return {"ok": False, "overallPass": False, "error": f"bad JSON: {e}", "raw": m.group(0)[:300], "checks": []}
    rows = verdict.get("checks", [])
    overall = bool(rows) and all(c.get("pass") for c in rows)
    return {"ok": True, "overallPass": overall, "checks": rows, "model": _vision_model(settings),
            "shot": str(shot), "context": context}


def judge(shot_path: str, rubric_name: str, context: str = "", settings: dict | None = None) -> dict:
    """Convenience: grade against a named RUBRIC."""
    checks = RUBRICS.get(rubric_name)
    if not checks:
        return {"ok": False, "overallPass": False, "error": f"unknown rubric '{rubric_name}'", "checks": []}
    r = judge_screenshot(shot_path, checks, context or rubric_name, settings)
    r["rubric"] = rubric_name
    return r
