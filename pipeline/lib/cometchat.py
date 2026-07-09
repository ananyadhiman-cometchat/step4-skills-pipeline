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
    masked = bool(stored) and stored != probe                     # extension rewrote the text
    blocked = code not in (200, 201)                              # extension rejected the send
    flagged = bool((resp.get("data", {}) or {}).get("moderation") or resp.get("moderation"))
    active = masked or blocked or flagged
    return {"sendCode": code, "active": active, "masked": masked, "blocked": blocked,
            "flagged": flagged, "sent": probe, "stored": stored[:160],
            "note": "moderation active" if active else "no moderation transform observed (extension likely not enabled in dashboard)"}


def seed_conversation(env_file, slug) -> dict:
    """Seed two namespaced users + a message between them → a real conversation to test."""
    cfg = _cfg(env_file)
    buyer, seller = f"{slug}-buy-001", f"{slug}-sel-001"
    r = {"buyer": create_user(cfg, buyer, "Bob Buyer", [f"uc:{slug}", "role:buyer"]),
         "seller": create_user(cfg, seller, "Sara Seller", [f"uc:{slug}", "role:seller"]),
         "seedMessage": send_message(cfg, seller, buyer, "Hi! Is the vintage camera still available?")}
    r["ok"] = r["buyer"] in (200, 201) and r["seller"] in (200, 201) and r["seedMessage"] in (200, 201)
    r["buyerUid"], r["sellerUid"] = buyer, seller
    return r
