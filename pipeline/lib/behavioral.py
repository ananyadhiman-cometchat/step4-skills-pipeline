"""Behavioral-verify tier (PIPELINE_RESILIENCE_PLAN §6 Phase 4).

Issue A from the review: the gates proved compile + boot + one chat message, so runtime features
(calling, role flows, new-chat) passed GREEN while broken, and humans found the bugs by hand.

This tier declares, per use case, the behavioral FEATURES that must be asserted at verify time, and —
crucially — a feature that cannot be proven in-harness records ``unverified`` (never a silent green).
The verify stage supplies pass/fail for the features it can actually run; everything else is surfaced
honestly. ``gate`` fails only on a real ``fail``; ``unverified`` is reported, not hidden.
"""
from __future__ import annotations

PASS, FAIL, UNVERIFIED = "pass", "fail", "unverified"


def _has(components, *kinds) -> bool:
    return any(c.get("kind") in kinds for c in components)


def _calls_family(components) -> bool:
    # calling is exercised by the mobile/app/native platforms in this matrix
    return _has(components, "app", "mobile", "android", "ios")


# feature registry: key, human title, applies(components), and whether it is verifiable in-harness
_FEATURES = [
    {"key": "chat-send-receive", "title": "Send a message and the other party receives it",
     "applies": lambda c: True, "verifiable": lambda c: True, "reason": ""},
    {"key": "role-matrix", "title": "Every role can log in and open chat",
     "applies": lambda c: _has(c, "backend"), "verifiable": lambda c: True, "reason": ""},
    {"key": "new-chat", "title": "Start a NEW conversation with someone (users list)",
     "applies": lambda c: _has(c, "web"), "verifiable": lambda c: True, "reason": ""},
    {"key": "call-connect", "title": "Voice/video call actually connects (media)",
     "applies": _calls_family, "verifiable": lambda c: False,
     "reason": "WebRTC media cannot connect on emulator/simulator — needs two physical devices"},
]


def plan(components: list[dict]) -> list[dict]:
    """The behavioral checklist for this use case: which features apply, and which are verifiable."""
    out = []
    for f in _FEATURES:
        if f["applies"](components):
            v = f["verifiable"](components)
            out.append({"key": f["key"], "title": f["title"], "verifiable": v,
                        "reason": "" if v else f["reason"]})
    return out


def run(components: list[dict], results: dict[str, bool] | None = None) -> list[dict]:
    """Combine the checklist with actual results the verify stage produced.
    ``results`` maps feature key -> bool (True=passed, False=failed) for the ones that were run.
    A verifiable feature with no result is ``unverified`` (the harness didn't run it — surface it)."""
    results = results or {}
    out = []
    for item in plan(components):
        key = item["key"]
        if not item["verifiable"]:
            status, detail = UNVERIFIED, item["reason"]
        elif key in results:
            status = PASS if results[key] else FAIL
            detail = "" if results[key] else "assertion failed"
        else:
            status, detail = UNVERIFIED, "no in-harness result was produced for this feature"
        out.append({"key": key, "title": item["title"], "status": status, "detail": detail})
    return out


def gate(statuses: list[dict]) -> bool:
    """Behavioral gate: pass unless something actually FAILED. Unverified is allowed but reported."""
    return not any(s["status"] == FAIL for s in statuses)
