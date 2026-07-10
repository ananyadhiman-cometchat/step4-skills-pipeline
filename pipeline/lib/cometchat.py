"""cometchat — REST API v3 helpers for the verify stage (seed users + a conversation).

Deterministic chat/call e2e needs both parties to exist in CometChat and a conversation
between them, independent of the app's own "message seller" flow. All UIDs namespaced
by the use-case slug (§6.1). Uses the provisioned app's REST API key.
"""
from __future__ import annotations
import json, os, urllib.request


def _cfg(env_file: str) -> dict:
    c = {}
    for line in open(os.path.expanduser(env_file)):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            c[k.strip()] = v.strip()
    return c


def _api(cfg: dict) -> str:
    return f"https://{cfg['COMETCHAT_APP_ID']}.api-{cfg['COMETCHAT_REGION']}.cometchat.io/v3"


def _req(url, cfg, method="POST", body=None, on_behalf=None):
    headers = {"apiKey": cfg["COMETCHAT_REST_API_KEY"], "appId": cfg["COMETCHAT_APP_ID"],
               "Content-Type": "application/json", "Accept": "application/json"}
    if on_behalf:
        headers["onBehalfOf"] = on_behalf
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as e:
        return 0, {"error": str(e)}


def create_user(cfg, uid, name, tags=None) -> int:
    body = {"uid": uid, "name": name, "tags": tags or []}
    code, resp = _req(f"{_api(cfg)}/users", cfg, body=body)
    if code in (200, 201):
        return 200
    # CometChat returns 400/409 with an "already exists" code for an existing UID — that's fine (idempotent)
    blob = json.dumps(resp).lower()
    if code in (400, 409) and ("already" in blob or "exist" in blob):
        return 200
    return code


def send_message(cfg, sender_uid, receiver_uid, text) -> int:
    body = {"category": "message", "type": "text", "receiverType": "user",
            "receiver": receiver_uid, "data": {"text": text}}
    code, _ = _req(f"{_api(cfg)}/messages", cfg, body=body, on_behalf=sender_uid)
    return code


def _send_message_full(cfg, sender_uid, receiver_uid, text):
    """Send a message and return (code, response) so the caller can read the stored/transformed text."""
    body = {"category": "message", "type": "text", "receiverType": "user",
            "receiver": receiver_uid, "data": {"text": text}}
    return _req(f"{_api(cfg)}/messages", cfg, body=body, on_behalf=sender_uid)


def check_moderation(env_file, slug) -> dict:
    """Functional AI-moderation probe. Sends a message carrying content moderation typically acts on
    (profanity + PII email/phone) and inspects what CometChat stored/returned. If the moderation /
    data-masking / profanity extension is enabled, the stored text is masked (e.g. '****') or the
    send is rejected/flagged. Read-only w.r.t. app state (uses a throwaway probe pair). Reports what
    is OBSERVED — a plain 'not configured' is an honest, valid result, recorded as a skills/setup gap."""
    cfg = _cfg(env_file)
    a, b = f"{slug}-modA-001", f"{slug}-modB-001"
    create_user(cfg, a, "Mod ProbeA", [f"uc:{slug}", "role:probe"])
    create_user(cfg, b, "Mod ProbeB", [f"uc:{slug}", "role:probe"])
    probe = "This is damn spam, email me at test@evil.com or call 555-123-4567"
    code, resp = _send_message_full(cfg, a, b, probe)
    stored = ""
    try:
        stored = (resp.get("data", {}) or {}).get("data", {}).get("text", "") or resp.get("data", {}).get("text", "")
    except Exception:
        stored = ""
    # A data-masking extension rewrites the DELIVERED copy, not necessarily the synchronous send-ack —
    # so re-fetch the stored message as the receiver and inspect the persisted text + moderation meta.
    refetched, moderated_meta = "", False
    try:
        _, got = _req(f"{_api(cfg)}/messages?per_page=10&category=message", cfg, method="GET", on_behalf=b)
        for m in reversed(got.get("data", []) if isinstance(got, dict) else []):
            d = m.get("data", {}) or {}
            t = d.get("text", "")
            if d.get("metadata", {}).get("@injected", {}).get("extensions", {}).get("data-masking") \
               or d.get("moderation"):
                moderated_meta = True
            if t:
                refetched = t
                break
    except Exception:
        pass
    masked = (bool(stored) and stored != probe) or (bool(refetched) and refetched != probe)  # text rewritten
    blocked = code not in (200, 201)                              # extension rejected the send
    flagged = moderated_meta or bool((resp.get("data", {}) or {}).get("moderation") or resp.get("moderation"))
    active = masked or blocked or flagged
    return {"sendCode": code, "active": active, "masked": masked, "blocked": blocked,
            "flagged": flagged, "sent": probe, "stored": stored[:160],
            "note": "moderation active" if active else "no moderation transform observed (extension likely not enabled in dashboard)"}


def call_answered(env_file, slug, since_ts, poll_s: int = 12, uid: str | None = None) -> dict:
    """Deterministic 'was the call answered?' — reads CometChat's SERVER-side call log via REST,
    independent of whether the browsers' WebRTC MEDIA held. Call messages carry an `action`:
    initiated → ongoing (ANSWERED) → ended. We look for an `ongoing` action newer than `since_ts`.
    Polls briefly because the server-side action lands a beat after the client accepts.
    Returns {answered, action?, sentAt?}. This is the anti-flake verdict for the headless call e2e.

    The reader uid defaults to the use case's ACTUAL web call-test uid (call_test_accounts) — the old
    hardcoded `{slug}-buy-001` exists only for mkt, so for every other use case this check silently
    returned answered=False and the 'media-independent anchor' was a no-op."""
    import time
    cfg = _cfg(env_file)
    reader = uid or call_test_accounts(slug)["web"][1]
    url = f"{_api(cfg)}/messages?per_page=40&category=call"
    deadline = time.time() + poll_s
    while True:
        code, resp = _req(url, cfg, method="GET", on_behalf=reader)
        for m in (resp.get("data", []) if isinstance(resp, dict) else []):
            action = (m.get("data", {}) or {}).get("action")
            if action == "ongoing" and int(m.get("sentAt", 0)) >= int(since_ts):
                return {"answered": True, "action": action, "sentAt": m.get("sentAt"), "type": m.get("type")}
        if time.time() >= deadline:
            return {"answered": False}
        time.sleep(2)


# Per-use-case call-test accounts (email, uid, display-name) for the two-party matrix. Generic
# default derives from the slug; mkt keeps its original buyer/seller pair for back-compat. The
# BACKEND seed of each use case MUST include these two accounts (mandated in the requirements/build
# prompt) so a client can log in as them and their CometChat uids line up with the seeded conversation.
CALL_TEST_OVERRIDE = {
    "mkt": {"mobile": ("sara.seller@mkt.io", "mkt-sel-001", "Sara Seller"),
            "web":    ("bob.buyer@mkt.io",   "mkt-buy-001", "Bob Buyer")},
}


def call_test_accounts(slug: str) -> dict:
    """Return {'mobile': (email, uid, name), 'web': (email, uid, name)} for the call matrix."""
    if slug in CALL_TEST_OVERRIDE:
        return CALL_TEST_OVERRIDE[slug]
    return {"mobile": (f"chat-a@{slug}.io", f"{slug}-cha-001", "Chat A"),
            "web":    (f"chat-b@{slug}.io", f"{slug}-chb-001", "Chat B")}


def seed_conversation(env_file, slug) -> dict:
    """Seed the two call-test users + a message between them → a real conversation to test. Uses the
    per-UC call_test_accounts so this works for ANY use case, not just the mkt buyer/seller pair."""
    cfg = _cfg(env_file)
    acc = call_test_accounts(slug)
    (m_email, m_uid, m_name) = acc["mobile"]
    (w_email, w_uid, w_name) = acc["web"]
    r = {"mobile": create_user(cfg, m_uid, m_name, [f"uc:{slug}", "role:calltest"]),
         "web": create_user(cfg, w_uid, w_name, [f"uc:{slug}", "role:calltest"]),
         "seedMessage": send_message(cfg, w_uid, m_uid, "Hi! (automated call-test seed)")}
    r["ok"] = r["mobile"] in (200, 201) and r["web"] in (200, 201) and r["seedMessage"] in (200, 201)
    r["mobileUid"], r["webUid"] = m_uid, w_uid
    r["buyerUid"], r["sellerUid"] = w_uid, m_uid   # legacy aliases
    return r
