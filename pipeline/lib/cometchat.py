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

    The reader uid MUST be a real participant in the call — callers pass the resolved chatPair uid.
    For mkt/del it can fall back to their override demo account; for any other use case with no uid we
    return answered=None (cannot determine — never invent a chat-a/chat-b reader), which the verdict
    treats as non-vetoing rather than a false 'not answered'."""
    import time
    cfg = _cfg(env_file)
    _ov = call_test_accounts(slug)
    reader = uid or (_ov["web"][1] if _ov else None)
    if not reader:
        return {"answered": None, "note": "no reader uid (pass the chatPair participant's uid)"}
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
    # del maps chat/call to its OWN demo accounts (courier ↔ customer, who share a seeded conversation) —
    # the chat-a/chat-b scaffold was removed so the live demo works with the demo accounts.
    "del": {"web":    ("customer@del.io", "del-cus-001", "Sam Customer"),
            "mobile": ("courier@del.io",  "del-cur-001", "Lena Courier")},
}


def call_test_accounts(slug: str) -> dict | None:
    """Real per-UC call-test accounts (mkt/del map chat/call to their OWN demo personas). Returns None
    for any other use case — the pair there comes from `uc['chatPair']` (two of the app's own seeded
    accounts), resolved by seed_and_resolve_pair. There is DELIBERATELY no invented chat-a/chat-b
    fallback: synthetic users rig the chat proof and pollute the real contact directory, and the harness
    bans an app from seeding them (verify.SYNTHETIC_SEED_ACCOUNTS)."""
    return CALL_TEST_OVERRIDE.get(slug)


def app_login(backend_url: str, email: str, password: str) -> dict:
    """Log into the APP backend to DISCOVER a user's CometChat uid — the login response carries
    `user.uid` (the CometChat identity the app maps this account to). Lets the harness test chat/call
    between the app's OWN existing demo accounts instead of a special chat-a/chat-b pair that has to be
    separately seeded (and drifts). Returns {email, uid, name, role} (uid None on failure)."""
    body = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(backend_url.rstrip("/") + "/api/auth/login", data=body,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read() or b"{}")
        u = d.get("user", {}) or {}
        # Capture cometchat_auth_token too: an EMPTY token here means the app's OWN login flow does not
        # provision/mint a CometChat identity for this account (e.g. login mints a token but never creates
        # the CometChat user), so REAL users can't chat — even though the harness later provisions the
        # chat-test pair out-of-band (which masks it). verify gates on this. Runs BEFORE any out-of-band
        # create_user, so it reflects the app's genuine behavior.
        return {"email": email, "uid": u.get("uid"), "name": u.get("name"), "role": u.get("role"),
                "cometchatAuthToken": d.get("cometchat_auth_token") or ""}
    except Exception as e:
        return {"email": email, "uid": None, "error": str(e)[:140], "cometchatAuthToken": ""}


def seed_and_resolve_pair(env_file: str, uc: dict, backend_url: str, password: str) -> dict:
    """Resolve the two chat-test parties from the app's OWN demo accounts (uc['chatPair'] = two seeded
    emails), discover their CometChat uid via app login, ensure both exist in CometChat, and seed a
    conversation between them. This decouples verification from the baseline seed (no chat-a/chat-b
    dependency, no drift). Returns {web:(email,uid,name), mobile:(email,uid,name), ok, mode}.
    Falls back to the legacy fixed chat-a/chat-b pair only when no chatPair is configured."""
    cfg = _cfg(env_file)
    slug = uc["slug"]
    # ALWAYS resolve the pair through the app's OWN /api/auth/login so we capture each account's
    # cometchat_auth_token — verify GATES on it being non-empty (an empty token means the app doesn't
    # provision a CometChat identity on login, so REAL users can't chat, even though create_user below
    # provisions the pair out-of-band). Default to the seeded chat-a/chat-b accounts when no chatPair is set.
    # The OLD "legacy fixed-chat-ab" branch that skipped app_login (and thus the token check) is REMOVED —
    # it silently let this exact false-positive through for the 8/10 use cases that have no chatPair.
    pair = uc.get("chatPair")
    if not (pair and len(pair) >= 2):
        # NO synthetic fallback. A UC without a chatPair must fail LOUDLY (the caller die_gates), never
        # silently invent chat-a/chat-b — that rigged the chat proof and polluted the contact directory.
        return {"web": (None, None, None), "mobile": (None, None, None), "ok": False,
                "mode": "no-chatpair", "loginError": "use_cases.json is missing chatPair for this UC"}
    a = app_login(backend_url, pair[0], password)   # web / receiver
    b = app_login(backend_url, pair[1], password)   # mobile / sender
    if a.get("uid") and b.get("uid"):
        # ensure both exist in CometChat (idempotent) + seed a message so a conversation exists
        create_user(cfg, a["uid"], a.get("name") or a["email"], [f"uc:{slug}", "role:calltest"])
        create_user(cfg, b["uid"], b.get("name") or b["email"], [f"uc:{slug}", "role:calltest"])
        sm = send_message(cfg, b["uid"], a["uid"], "Hi! (automated call-test seed)")
        return {"web": (a["email"], a["uid"], a.get("name")),
                "mobile": (b["email"], b["uid"], b.get("name")),
                "ok": sm in (200, 201), "mode": "app-demo-accounts", "logins": {"a": a, "b": b}}
    return {"web": (pair[0], a.get("uid"), None), "mobile": (pair[1], b.get("uid"), None),
            "ok": False, "mode": "app-demo-accounts", "loginError": {"a": a, "b": b}}
